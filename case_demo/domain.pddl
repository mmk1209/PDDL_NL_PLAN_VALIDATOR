(define (domain mobileworld_generic)
  ;; Generic MobileWorld domain (task-agnostic), improved:
  ;; 1) status complete must be the LAST action (finalization lock).
  ;; 2) input_text requires the text to be READY (supports causal chains from MCP outputs).
  ;; 3) typing allowed only when the focused field is visible on the current screen.
  ;; 4) focus is cleared on any screen transition; focus actions enforce single-focus.

  (:requirements
    :strips
    :typing
    :negative-preconditions
    :action-costs
    :equality
    :existential-preconditions
    :universal-preconditions
    :conditional-effects
  )

  (:types
    screen target field direction
    text
    goal_status
    tool param deliverable
  )

  (:constants
    home - screen
  )

  (:predicates
    ;; -----------------------
    ;; GUI / navigation state
    ;; -----------------------
    (at-screen ?s - screen)
    (focused ?f - field)

    (target-visible ?t - target ?s - screen)
    (field-visible  ?f - field  ?s - screen)

    (back-link ?from ?to - screen)

    ;; -----------------------
    ;; UI semantics hooks
    ;; -----------------------
    (click-transition ?t - target ?from ?to - screen)
    (doubletap-transition ?t - target ?from ?to - screen)
    (longpress-transition ?t - target ?from ?to - screen)

    (click-focus ?t - target ?s - screen ?f - field)
    (doubletap-focus ?t - target ?s - screen ?f - field)
    (longpress-focus ?t - target ?s - screen ?f - field)

    (drag-transition ?t1 ?t2 - target ?from ?to - screen)
    (scroll-transition ?d - direction ?from ?to - screen)
    (enter-transition ?from ?to - screen)

    ;; -----------------------
    ;; Text & task-control bookkeeping
    ;; -----------------------
    (text-entered ?txt - text)
    (field-has-text ?f - field ?txt - text)

    (answered ?txt - text)
    (asked-user ?txt - text)
    (status-set ?gs - goal_status)

    ;; NEW: text readiness gate (task-agnostic)
    (text-ready ?txt - text)

    ;; NEW: finalization lock (task-agnostic)
    (finalized)

    ;; -----------------------
    ;; MCP tool call modeling
    ;; -----------------------
    (tool-available ?tool - tool)
    (param-for-tool ?par - param ?tool - tool)
    (called ?par - param)

    (mcp-produces ?par - param ?d - deliverable)
    (have ?d - deliverable)
  )

  (:functions
    (total-cost) - number
  )

  ;; ============================================================
  ;; Helper effects used inline
  ;; ============================================================

  ;; ============================================================
  ;; GUI operations
  ;; ============================================================

  (:action click_navigate
    :parameters (?t - target ?from ?to - screen)
    :precondition (and
      (not (finalized))
      (at-screen ?from)
      (target-visible ?t ?from)
      (click-transition ?t ?from ?to)
    )
    :effect (and
      (not (at-screen ?from))
      (at-screen ?to)
      ;; clear focus when switching screens
      (forall (?f - field) (when (focused ?f) (not (focused ?f))))
      (increase (total-cost) 1)
    )
  )

  (:action click_focus_field
    :parameters (?t - target ?s - screen ?f - field)
    :precondition (and
      (not (finalized))
      (at-screen ?s)
      (target-visible ?t ?s)
      (field-visible ?f ?s)
      (click-focus ?t ?s ?f)
    )
    :effect (and
      ;; enforce single-focus
      (forall (?g - field) (when (focused ?g) (not (focused ?g))))
      (focused ?f)
      (increase (total-cost) 1)
    )
  )

  (:action double_tap_navigate
    :parameters (?t - target ?from ?to - screen)
    :precondition (and
      (not (finalized))
      (at-screen ?from)
      (target-visible ?t ?from)
      (doubletap-transition ?t ?from ?to)
    )
    :effect (and
      (not (at-screen ?from))
      (at-screen ?to)
      (forall (?f - field) (when (focused ?f) (not (focused ?f))))
      (increase (total-cost) 1)
    )
  )

  (:action double_tap_focus_field
    :parameters (?t - target ?s - screen ?f - field)
    :precondition (and
      (not (finalized))
      (at-screen ?s)
      (target-visible ?t ?s)
      (field-visible ?f ?s)
      (doubletap-focus ?t ?s ?f)
    )
    :effect (and
      (forall (?g - field) (when (focused ?g) (not (focused ?g))))
      (focused ?f)
      (increase (total-cost) 1)
    )
  )

  (:action long_press_navigate
    :parameters (?t - target ?from ?to - screen)
    :precondition (and
      (not (finalized))
      (at-screen ?from)
      (target-visible ?t ?from)
      (longpress-transition ?t ?from ?to)
    )
    :effect (and
      (not (at-screen ?from))
      (at-screen ?to)
      (forall (?f - field) (when (focused ?f) (not (focused ?f))))
      (increase (total-cost) 1)
    )
  )

  (:action long_press_focus_field
    :parameters (?t - target ?s - screen ?f - field)
    :precondition (and
      (not (finalized))
      (at-screen ?s)
      (target-visible ?t ?s)
      (field-visible ?f ?s)
      (longpress-focus ?t ?s ?f)
    )
    :effect (and
      (forall (?g - field) (when (focused ?g) (not (focused ?g))))
      (focused ?f)
      (increase (total-cost) 1)
    )
  )

  (:action drag_navigate
    :parameters (?t1 ?t2 - target ?from ?to - screen)
    :precondition (and
      (not (finalized))
      (at-screen ?from)
      (target-visible ?t1 ?from)
      (target-visible ?t2 ?from)
      (drag-transition ?t1 ?t2 ?from ?to)
    )
    :effect (and
      (not (at-screen ?from))
      (at-screen ?to)
      (forall (?f - field) (when (focused ?f) (not (focused ?f))))
      (increase (total-cost) 1)
    )
  )

  ;; IMPORTANT:
  ;; - must be focused
  ;; - must be on a screen where the field is visible
  ;; - text must be READY
  (:action input_text
    :parameters (?f - field ?txt - text)
    :precondition (and
      (not (finalized))
      (focused ?f)
      (text-ready ?txt)
      (exists (?s - screen)
        (and (at-screen ?s) (field-visible ?f ?s))
      )
    )
    :effect (and
      (text-entered ?txt)
      (field-has-text ?f ?txt)
      (increase (total-cost) 1)
    )
  )

  (:action scroll
    :parameters (?d - direction ?from ?to - screen)
    :precondition (and
      (not (finalized))
      (at-screen ?from)
      (scroll-transition ?d ?from ?to)
    )
    :effect (and
      (not (at-screen ?from))
      (at-screen ?to)
      (forall (?f - field) (when (focused ?f) (not (focused ?f))))
      (increase (total-cost) 1)
    )
  )

  ;; ============================================================
  ;; Navigation
  ;; ============================================================

  (:action navigate_home
    :parameters (?from - screen)
    :precondition (and
      (not (finalized))
      (at-screen ?from)
      (not (= ?from home))
    )
    :effect (and
      (not (at-screen ?from))
      (at-screen home)
      (forall (?f - field) (when (focused ?f) (not (focused ?f))))
      (increase (total-cost) 1)
    )
  )

  (:action navigate_back
    :parameters (?from ?to - screen)
    :precondition (and
      (not (finalized))
      (at-screen ?from)
      (back-link ?from ?to)
    )
    :effect (and
      (not (at-screen ?from))
      (at-screen ?to)
      (forall (?f - field) (when (focused ?f) (not (focused ?f))))
      (increase (total-cost) 1)
    )
  )

  (:action keyboard_enter
    :parameters (?from ?to - screen)
    :precondition (and
      (not (finalized))
      (at-screen ?from)
      (enter-transition ?from ?to)
    )
    :effect (and
      (not (at-screen ?from))
      (at-screen ?to)
      (forall (?f - field) (when (focused ?f) (not (focused ?f))))
      (increase (total-cost) 1)
    )
  )

  (:action wait
    :parameters ()
    :precondition (and
      (not (finalized))
    )
    :effect (and
      (increase (total-cost) 1)
    )
  )

  ;; ============================================================
  ;; Task control
  ;; ============================================================

  (:action answer
    :parameters (?txt - text)
    :precondition (and
      (not (finalized))
      (text-ready ?txt)   ;; optional but consistent: only answer ready text
    )
    :effect (and
      (answered ?txt)
      (increase (total-cost) 1)
    )
  )

  (:action ask_user
    :parameters (?txt - text)
    :precondition (and
      (not (finalized))
    )
    :effect (and
      (asked-user ?txt)
      (increase (total-cost) 1)
    )
  )

  ;; status is the TERMINAL action: once executed, the task is finalized.
  (:action status
    :parameters (?gs - goal_status)
    :precondition (and
      (not (finalized))
    )
    :effect (and
      (status-set ?gs)
      (finalized)
      (increase (total-cost) 1)
    )
  )

  ;; ============================================================
  ;; MCP call
  ;; ============================================================

  (:action mcp_call
    :parameters (?tool - tool ?par - param ?d - deliverable)
    :precondition (and
      (not (finalized))
      (tool-available ?tool)
      (param-for-tool ?par ?tool)
      (mcp-produces ?par ?d)
      (not (called ?par))
    )
    :effect (and
      (called ?par)
      (have ?d)
      (increase (total-cost) 1)
    )
  )

  ;; ============================================================
  ;; NEW: generic "materialize text from deliverable"
  ;; This is intentionally task-agnostic: any deliverable can be turned into any ready text.
  ;; The problem (or executor) decides what the deliverable contains and how the text is formed.
  ;; ============================================================
  (:action make_text_ready_from_deliverable
    :parameters (?d - deliverable ?txt - text)
    :precondition (and
      (not (finalized))
      (have ?d)
    )
    :effect (and
      (text-ready ?txt)
      (increase (total-cost) 1)
    )
  )
)
