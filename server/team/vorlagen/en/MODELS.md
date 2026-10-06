# Which model for which work

Two dials, not one: **model** and **effort**. The second is easy to overlook —
the default would be `xhigh`, which is a waste for routine work.

| Model | Input $/1M | Output $/1M | Context |
|---|---|---|---|
| `fable` | 10.00 | 50.00 | 1M |
| `opus` | 5.00 | 25.00 | 1M |
| `sonnet` | 2.00 | 10.00 | 1M |
| `haiku` | 1.00 | 5.00 | **200K** |

Between top and bottom there's a **factor of 10**.

## Assignment

| Kind of work | Model | Effort |
|---|---|---|
| Running the company, briefings, decisions | `opus` | `high` |
| Complex code, architecture | `opus` | `xhigh` |
| Regular implementation (frontend, backend) | `sonnet` | `high` |
| Code review | `sonnet` | `high` |
| Research, reading docs, summarizing | `sonnet` | `low` |
| Running tests, checking output, logging | `haiku` | `low` |
| Conversation, calendar, email | `sonnet` | `medium` |

**Nobody gets `fable` for now.** It uses twice as much quota as `opus`. If at
all, then as a deliberate one-off decision for a specific hard task — not as a
feature of a role.

## Two rules that are often gotten wrong

**The stronger model on low effort often beats the weaker one on high.**
Before anyone is put on `haiku`, `sonnet` + `low` is the first alternative —
usually cheaper *and* better.

**Measure per completed task, not per request.** Whoever has to ask three
times isn't cheap — every follow-up pushes the task closer to the brakes. An
under-resourced reviewer costs more than a pricier one who gets it right the
first time.

## Haiku only has 200K context

All others 1M. Doesn't matter for short, contained turns; it does for
anything sprawling.
