(define (problem fallback_demo)
  (:domain mobileworld_generic)

  (:objects
    home_screen search_screen results_screen - screen
    search_button back_button - target
    search_field - field
    query_text - text
    success_status - goal_status
    up down - direction
  )

  (:init
    (at-screen home_screen)

    (target-visible search_button home_screen)
    (field-visible search_field home_screen)

    (click-transition search_button home_screen search_screen)
    (back-link search_screen home_screen)

    (scroll-transition down search_screen results_screen)
  )

  (:goal
    (and
      (status-set success_status)
    )
  )
)