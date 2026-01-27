(define (problem contacts_message_long_v1)
  (:domain mobileworld_generic)

  (:objects
    ;; -------- screens --------
    s_contacts
    s_contacts_list
    s_contact_alice
    s_message_editor
    s_sent
    - screen

    ;; -------- targets --------
    t_contacts_icon
    t_scroll_anchor
    t_alice_entry
    t_message_button
    t_body_field
    t_send_button
    - target

    ;; -------- fields --------
    f_body - field

    ;; -------- directions --------
    down - direction

    ;; -------- texts --------
    txt_auto_reply - text

    ;; -------- goal status --------
    complete infeasible - goal_status

    ;; -------- tools / params / deliverables --------
    tool_llm - tool
    par_generate_reply - param
    d_reply_text - deliverable
  )

  (:init
    ;; ===== initial screen =====
    (at-screen home)

    ;; ===== tool availability =====
    (tool-available tool_llm)
    (param-for-tool par_generate_reply tool_llm)
    (mcp-produces par_generate_reply d_reply_text)

    ;; ===== visibility =====
    (target-visible t_contacts_icon home)

    (scroll-transition down s_contacts s_contacts_list)

    (target-visible t_scroll_anchor s_contacts)

    (target-visible t_alice_entry s_contacts_list)

    (target-visible t_message_button s_contact_alice)

    (target-visible t_body_field s_message_editor)
    (target-visible t_send_button s_message_editor)
    (field-visible  f_body s_message_editor)

    ;; ===== transitions =====
    (click-transition t_contacts_icon home s_contacts)

    (click-transition t_alice_entry s_contacts_list s_contact_alice)

    (click-transition t_message_button s_contact_alice s_message_editor)

    (click-transition t_send_button s_message_editor s_sent)

    ;; focus mapping
    (click-focus t_body_field s_message_editor f_body)

    ;; back links
    (back-link s_sent s_message_editor)
    (back-link s_message_editor s_contact_alice)
    (back-link s_contact_alice s_contacts_list)
    (back-link s_contacts_list s_contacts)
    (back-link s_contacts home)

    ;; ===== cost =====
    (= (total-cost) 0)
  )

  (:goal (and
    ;; must have message text in body
    (field-has-text f_body txt_auto_reply)

    ;; must return home
    (at-screen home)

    ;; must finalize
    (status-set complete)
  ))

  (:metric minimize (total-cost))
)
