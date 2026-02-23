# Ticket Plan Format

When presenting an action plan to the user, always use this visual format. This ensures consistency and makes it easy to review and approve before execution.

## Create / Bulk Create Plan

```
======================================================================
  JIRA TICKET CREATION PLAN
======================================================================
  Epic: API-8291
----------------------------------------------------------------------
  #      Action   SP     Summary
----------------------------------------------------------------------
  S1     CREATE    2.0   Foundation & Shared Infrastructure
    1.1  CREATE    0.5   Set Up Python Environment
    1.2  CREATE    0.5   Build Shared Generator Framework
    1.3  SKIP      0.5   Build Shared Validator Framework [API-8310]
  S2     CREATE    2.0   Evaluation Framework
    2.1  CREATE    0.5   Set Up Langfuse Integration
----------------------------------------------------------------------
  Creates: 4  |  Skips: 1  |  Total: 5
======================================================================
```

## Update Plan

```
======================================================================
  JIRA TICKET UPDATE PLAN
======================================================================
  #      Key           Field          Old -> New
----------------------------------------------------------------------
  1      API-8301      summary        "Foundation" -> "Foundation v2"
  2      API-8301      story_points   2.0 -> 3.0
  3      API-8310      description    (changed, 150 chars diff)
----------------------------------------------------------------------
  Updates: 3
======================================================================
```

## Delete Plan

```
======================================================================
  JIRA TICKET DELETE PLAN
======================================================================
  #      Key           Type       Summary
----------------------------------------------------------------------
  1      API-8310      Sub-task   Build Shared Validator Framework
  2      API-8311      Sub-task   Create SDK Registry Data Source
----------------------------------------------------------------------
  Deletes: 2  (subtasks will also be deleted: 0)
======================================================================
```

## Estimation Validation Report

```
========================================================================
  ESTIMATION VALIDATION REPORT
========================================================================
  Epic: API-8291 — Cap Agent Kit
------------------------------------------------------------------------
  Story            Estimate  Sub Sum   #Subs  Status
------------------------------------------------------------------------
  API-8301 (S1)        2.0       2.0       5  OK
  API-8302 (S2)        2.0       2.0       4  OK
  API-8303 (S3)        2.0       1.5       4  MISMATCH (-0.5)
------------------------------------------------------------------------
  Epic Total          15.0      14.5              MISMATCH (-0.5)
------------------------------------------------------------------------
  1 mismatch(es) found.
========================================================================
```

## Rules

1. Always show the plan before executing any create, update, or delete operation
2. Ask: **"Proceed with this plan? (yes / no / edit)"**
3. If the user says "edit", ask what they want to change and present the updated plan again
4. Only proceed after explicit "yes" or equivalent confirmation
5. For delete operations, emphasize that deletion is irreversible
6. For estimation validation, automatically offer to run after bulk create completes
