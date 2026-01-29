# -*- coding: utf-8 -*-
"""Local-only LLM caller for HuggingFace models (e.g., Qwen)."""

import os
import time
import random
from typing import Optional, Dict, List
from datetime import datetime

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, will use system environment variables


class LocalLLMCaller:
    """Local-only caller with simple retry logic."""

    # Class constants
    MAX_RETRY_ATTEMPTS = 10
    def __init__(
        self,
        model: str = "local:Qwen/Qwen3-4B-Instruct-2507",
        base_retry_delay: float = 2.0,
        max_retry_delay: float = 60.0,
        jitter: float = 0.1,
        max_attempts: Optional[int] = None
    ):
        """Initialize local LLM caller with retry logic.

        Args:
            model: Model name to use
            base_retry_delay: Base retry delay in seconds
            max_retry_delay: Maximum retry delay in seconds
            jitter: Random jitter range to avoid simultaneous retries
            max_attempts: Maximum number of attempts (None for unlimited)
        """
        self.model = model.split(":", 1)[1] if ":" in model else model
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.tokenizer = AutoTokenizer.from_pretrained(self.model, trust_remote_code=True)
        torch_dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.local_model = AutoModelForCausalLM.from_pretrained(
            self.model,
            torch_dtype=torch_dtype,
            device_map="auto" if self.device == "cuda" else None,
            trust_remote_code=True
        )
        if hasattr(self.local_model, "hf_device_map") and self.local_model.hf_device_map:
            self.input_device = next(iter(self.local_model.hf_device_map.values()))
        else:
            self.input_device = self.device
        self.max_input_tokens = self.tokenizer.model_max_length
        self.encoder = self.tokenizer

        self.base_retry_delay = max(1.0, base_retry_delay)
        self.max_retry_delay = max(self.base_retry_delay, max_retry_delay)
        self.jitter = min(1.0, max(0.0, jitter))
        self.max_attempts = max_attempts

        self.reset_stats()
        
    def count_input_tokens(self, prompt: str, system_instruction: str) -> Dict[str, int]:
        """预计算输入token数量"""
        prompt_tokens = self.encoder.encode(prompt)
        system_tokens = self.encoder.encode(system_instruction)
        total_tokens = prompt_tokens + system_tokens
        
        return {
            "prompt_tokens": prompt_tokens,
            "system_tokens": system_tokens,
            "total_tokens": total_tokens
        }

    
    def reset_stats(self):
        """重置统计信息"""
        self.attempt_count = 0
        self.start_time = None
        self.total_delay = 0
    
    def _calculate_delay(self) -> float:
        """计算下一次重试的延迟时间"""
        delay = min(
            self.max_retry_delay,
            self.base_retry_delay * (2 ** (self.attempt_count - 1))
        )
        
        if self.jitter > 0:
            jitter_amount = delay * self.jitter
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(self.base_retry_delay, min(delay, self.max_retry_delay))
    
    def _handle_error(self, error: Exception) -> float:
        """处理错误并返回等待时间"""
        error_type = type(error).__name__
        error_message = str(error)
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # 认证错误直接返回None
        if "AuthenticationError" in error_type:
            print(f"[{current_time}] 认证错误，跳过此次请求")
            return -1  # 特殊标记，表示需要直接返回None
        
        # 处理其他错误
        if "RateLimitError" in error_type:
            wait_time = self._calculate_delay() + 10
            print(f"[{current_time}] 遇到频率限制 ({error_message})")
        elif "TimeoutError" in error_type:
            wait_time = self._calculate_delay()
            print(f"[{current_time}] 请求超时 ({error_message})")
        elif "APIError" in error_type or "APIConnectionError" in error_type:
            wait_time = self._calculate_delay() + 5
            print(f"[{current_time}] API错误 ({error_message})")
        else:
            wait_time = self._calculate_delay()
            print(f"[{current_time}] 未知错误 {error_type} ({error_message})")
        
        # 检查是否达到最大尝试次数
        if self.max_attempts and self.attempt_count >= self.max_attempts:
            print(f"达到最大尝试次数 {self.max_attempts}，跳过此次请求")
            return -1  # 特殊标记，表示需要直接返回None
        
        print(f"第 {self.attempt_count} 次尝试失败，等待 {wait_time:.1f} 秒后重试...")
        return wait_time
    
    def get_completion(self, prompt: str, system_instruction: str = "", temperature: float = 1.0, n: int = 1, max_new_tokens: int = 512, verbose: bool = False):
        """仅使用本地模型生成回复，带简单重试。"""
        self.reset_stats()
        token_stats = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        start_time = time.time()
        

        total_attempt_count = 0
        responses = []
        total_time = 0
        for _ in range(n):

            self.attempt_count = 0
            while self.attempt_count < self.MAX_RETRY_ATTEMPTS:
                self.attempt_count += 1
                try:
                    # ===== 构造 Chat Messages =====
                    messages = []
                    if system_instruction:
                        messages.append({"role": "system", "content": system_instruction})
                    messages.append({"role": "user", "content": prompt})

                    # ===== 使用 Qwen Chat Template =====
                    prompt_text = self.tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True   # 关键！
                    )

                    inputs = self.tokenizer(prompt_text, return_tensors="pt").to(self.input_device)
                    input_len = inputs.input_ids.shape[1]

                    with torch.no_grad():
                        outputs = self.local_model.generate(
                            **inputs,
                            max_new_tokens=max_new_tokens,
                            temperature=temperature if temperature > 0 else 0.3,
                            do_sample=True,
                            repetition_penalty=1.1,
                            eos_token_id=self.tokenizer.eos_token_id,
                        )

                    # ===== 只截取模型新生成的部分（非常重要）=====
                    generated_ids = outputs[0][input_len:]
                    decoded = self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

                    responses.append(decoded)
                    token_stats = self.get_num_tokens_local(inputs, outputs)

                    token_stats = self.get_num_tokens_local(inputs, outputs)
                    total_time += time.time() - start_time
                    total_attempt_count += self.attempt_count
                    break
                    
                    
                    
                except Exception as e:
                    wait_time = self._handle_error(e)
                    
                    if wait_time == -1:
                        total_attempt_count += self.attempt_count
                        break
                    
                    self.total_delay += wait_time
                    time.sleep(wait_time)
                    
        if verbose:
            print(f"\n成功获取{len(responses)}/{running_n*n}个回复! 总耗时: {total_time:.1f}秒，尝试次数: {total_attempt_count}")
        
        return responses, token_stats
            
    def get_num_tokens(self, response):
        prompt_tokens = response.usage.prompt_tokens 
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": total_tokens}

    def get_num_tokens_local(self, inputs, outputs):
        prompt_tokens = inputs.input_ids.shape[1]
        # assume all outputs same length
        completion_tokens = outputs[0].shape[0] - prompt_tokens
        total_tokens = prompt_tokens + completion_tokens
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens
        }

def main():
    # 默认使用本地 Qwen；可通过 MODEL_NAME 覆盖，例如:
    #   MODEL_NAME="local:Qwen/Qwen3-4B-Instruct-2507"
    model_name = os.getenv("MODEL_NAME", "local:Qwen/Qwen3-4B-Instruct-2507")
    caller = LocalLLMCaller(
        model=model_name,
        base_retry_delay=2.0,
        max_retry_delay=60.0,
        jitter=0.1,
        max_attempts=3  # 设置最大尝试次数
    )
    
    # 测试多个问题
    prompts = [
        "你好，请介绍一下自己。",
        # "什么是人工智能？",
        # "请解释一下量子计算。"
    ]
    
    for i, prompt in enumerate(prompts, 1):
        print(f"\n=== 问题 {i} ===")
        print(f"提示词: {prompt}\n")
        
        response, token_stats = caller.get_completion(prompt)
        print(token_stats)
        if not response:
            print(f"问题 {i} 跳过，继续下一个问题")
        else:
            print(f"\n回复 {i}:")
            print(response)

if __name__ == "__main__":
    main()
