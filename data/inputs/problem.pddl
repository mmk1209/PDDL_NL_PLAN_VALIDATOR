(define (problem mw_reply_daniel_most_recent_email_v1)
  (:domain mobileworld_generic)

  (:objects
    ;; ---------- screens ----------
    s_gmail_inbox
    s_email_daniel_most_recent
    s_reply_compose
    s_gmail_sent
    - screen

    ;; ---------- targets ----------
    t_gmail_icon
    t_daniel_most_recent_email
    t_reply_button
    t_body_field
    t_send_button
    - target

    ;; ---------- fields ----------
    f_body - field

    ;; ---------- directions ----------
    up down left right - direction

    ;; ---------- texts ----------
    txt_reply_to_daniel_10am_thu - text

    ;; ---------- goal status ----------
    complete infeasible - goal_status

    ;; ---------- tool/param/deliverable ----------
    ;; (not needed for this task)
  )

  (:init
    ;; ===== initial UI state =====
    (at-screen home)

    ;; ===== Text readiness =====
    ;; The reply sentence is a constant -> ready immediately.
    (text-ready txt_reply_to_daniel_10am_thu)

    ;; ===== UI visibility =====
    (target-visible t_gmail_icon home)

    ;; In inbox, the most recent email from Daniel is visible as a target
    (target-visible t_daniel_most_recent_email s_gmail_inbox)

    ;; In Daniel email detail screen, Reply button visible
    (target-visible t_reply_button s_email_daniel_most_recent)

    ;; In reply compose screen, body field + send visible
    (target-visible t_body_field s_reply_compose)
    (target-visible t_send_button s_reply_compose)

    (field-visible f_body s_reply_compose)

    ;; ===== UI transitions =====
    ;; Open Gmail
    (click-transition t_gmail_icon home s_gmail_inbox)

    ;; Open Daniel's most recent email
    (click-transition t_daniel_most_recent_email s_gmail_inbox s_email_daniel_most_recent)

    ;; Tap Reply -> goes to reply compose
    (click-transition t_reply_button s_email_daniel_most_recent s_reply_compose)

    ;; Send -> sent screen
    (click-transition t_send_button s_reply_compose s_gmail_sent)

    ;; Focus mapping
    (click-focus t_body_field s_reply_compose f_body)

    ;; Back links (optional)
    (back-link s_reply_compose s_email_daniel_most_recent)
    (back-link s_email_daniel_most_recent s_gmail_inbox)
    (back-link s_gmail_inbox home)

    ;; ===== cost init =====
    (= (total-cost) 0)
  )

  (:goal (and
    ;; Must have typed the reply content into body
    (field-has-text f_body txt_reply_to_daniel_10am_thu)

    ;; Must have sent the reply (reach sent screen)
    (at-screen s_gmail_sent)

    ;; Must finalize the task
    (status-set complete)
  ))

  (:metric minimize (total-cost))
)
