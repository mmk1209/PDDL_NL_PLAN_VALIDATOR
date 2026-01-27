(define (problem search_input_return_v1)
  (:domain mobileworld_generic)

  (:objects
    ;; -------- screens --------
    s_search - screen

    ;; -------- targets --------
    t_search_icon
    t_search_field
    - target

    ;; -------- fields --------
    f_query - field

    ;; -------- directions --------
    up down - direction

    ;; -------- texts --------
    txt_pddl - text

    ;; -------- goal status --------
    complete infeasible - goal_status
  )

  (:init
    ;; ===== initial screen =====
    (at-screen home)

    ;; ===== text readiness =====
    (text-ready txt_pddl)

    ;; ===== visibility =====
    (target-visible t_search_icon home)

    (target-visible t_search_field s_search)
    (field-visible  f_query s_search)

    ;; ===== transitions =====
    ;; home -> search
    (click-transition t_search_icon home s_search)

    ;; focus mapping
    (click-focus t_search_field s_search f_query)

    ;; back navigation
    (back-link s_search home)

    ;; ===== cost =====
    (= (total-cost) 0)
  )

  (:goal (and
    ;; must have entered text
    (field-has-text f_query txt_pddl)

    ;; must return to home
    (at-screen home)

    ;; must finalize
    (status-set complete)
  ))

  (:metric minimize (total-cost))
)
