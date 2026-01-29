(define (problem search_transformer)

  (:domain mobileworld_generic)

  (:objects
    home - screen
    home_screen search_screen results_screen - screen
    search_field result_field - field
    start_text query_text result_text - text
    success_status - goal_status
    data_deliverable - deliverable
    search_button result_button - target
    down up - direction
    data_extractor - tool
    query_param - param
  )

  (:init
    (at-screen home)
    (target-visible search_button search_screen)
    (target-visible result_button results_screen)
    (field-visible search_field search_screen)
    (field-visible result_field results_screen)
    (click-transition search_button home results_screen)
    (click-transition result_button results_screen home)
    (doubletap-transition search_button home results_screen)
    (longpress-transition result_button results_screen home)
    (drag-transition search_button result_button home results_screen)
    (scroll-transition down home search_screen)
    (scroll-transition up search_screen results_screen)
    (back-link results_screen home)
    (text-ready start_text)
    (text-ready query_text)
    (text-ready result_text)
    (tool-available data_extractor)
    (param-for-tool query_param data_extractor)
    (mcp-produces query_param data_deliverable)
    (have data_deliverable)
  )

  (:goal
    (and
      (at-screen results_screen)
      (field-has-text search_field query_text)
      (answered result_text)
      (status-set success_status)
    )
  )

  ;(:metric :sumOfCosts)
)