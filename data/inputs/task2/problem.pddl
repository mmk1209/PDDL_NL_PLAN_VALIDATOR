(define (problem notes_write_hello_v1)
  (:domain mobileworld_generic)

  (:objects
    ;; -------- screens --------
    s_notes
    s_editor
    s_saved
    - screen

    ;; -------- targets --------
    t_notes_icon
    t_new_note
    t_body_field
    t_save_button
    - target

    ;; -------- fields --------
    f_body - field

    ;; -------- directions --------
    up down - direction

    ;; -------- texts --------
    txt_hello - text

    ;; -------- goal status --------
    complete infeasible - goal_status
  )

  (:init
    ;; ===== initial screen =====
    (at-screen home)

    ;; ===== text readiness =====
    (text-ready txt_hello)

    ;; ===== visibility =====
    (target-visible t_notes_icon home)

    (target-visible t_new_note s_notes)

    (target-visible t_body_field s_editor)
    (target-visible t_save_button s_editor)
    (field-visible  f_body s_editor)

    ;; ===== transitions =====
    ;; home -> notes
    (click-transition t_notes_icon home s_notes)

    ;; notes -> editor
    (click-transition t_new_note s_notes s_editor)

    ;; save -> saved
    (click-transition t_save_button s_editor s_saved)

    ;; focus body field
    (click-focus t_body_field s_editor f_body)

    ;; back links (optional)
    (back-link s_editor s_notes)
    (back-link s_notes home)

    ;; ===== cost =====
    (= (total-cost) 0)
  )

  (:goal (and
    ;; text must be typed
    (field-has-text f_body txt_hello)

    ;; must reach saved screen
    (at-screen s_saved)

    ;; must finalize
    (status-set complete)
  ))

  (:metric minimize (total-cost))
)
