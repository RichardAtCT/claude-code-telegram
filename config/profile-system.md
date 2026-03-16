# User Profile System — Revised Design

## 1. Profile File

**Location:** `profiles/user.md` (single user, no ID needed)

**Format:** Three-section markdown, owned and maintained by the agent.

```markdown
# User Profile

## Soul & Motivation
[What drives this person — values, aspirations, what they care about vs. what they think they should care about]

## Decision Framework
[Learned rules for making prioritization calls — relative priorities, constraints, scheduling patterns, known anti-patterns]

## Patterns
[Observed behavioral data — completion tendencies, energy patterns, what coaching approaches work, recurring failure modes]
```

The agent reads this file at the start of every session and writes to it when it learns something new. Claude Code's native file tools (Read/Edit/Write) handle all access — no custom tooling needed.

---

## 2. Learning Triggers

Four triggers cause the agent to update the profile. Here's what each one looks like in practice:

### Trigger 1: Explicit Value Statement

**When:** The user says something that directly reveals a value or priority.

Examples:
- "Health is more important to me than career right now"
- "I don't actually care about the promotion, I care about learning"
- "Family always comes first on weekends"

**Agent action:** Update Soul & Motivation and/or Decision Framework immediately, in the same session. The agent acknowledges the update conversationally ("Noted — I'll weight health over career in future recommendations").

### Trigger 2: Repeated Outcome Pattern

**When:** The agent notices a pattern in goal outcomes over 5+ data points.

Examples:
- User completes fitness goals 90% of the time but skips study goals 60% of the time
- User always skips goals on Wednesdays
- User succeeds when goals are framed as "30 minutes of X" but fails when framed as "finish X"

**Agent action:** Update the Patterns section. This typically happens during an evening check-in or weekly review — not mid-morning when the user is busy. The agent mentions it: "I've noticed you skip study goals when they're after 8pm. Moving to mornings."

### Trigger 3: Coaching Feedback

**When:** The user gives feedback on how the agent is operating.

Examples:
- "Stop checking in so often"
- "I like when you give me the reasoning, keep doing that"
- "Don't suggest fitness on Mondays, that's my rest day"

**Agent action:** Update Decision Framework (for scheduling/approach rules) or Patterns (for coaching style preferences). Immediate, same session.

### Trigger 4: Goal Restructuring

**When:** The user drops, adds, or significantly changes a goal.

Examples:
- "I'm dropping the writing goal — it's not the right time"
- "Actually, I want to pivot from system design to distributed systems"
- Onboarding (initial goal setup)

**Agent action:** Update Soul & Motivation if the "why" changes, Decision Framework if priorities shift. Record in the same session as the goal change.

### How the Agent Decides (Mechanically)

The agent doesn't run a separate "should I update the profile?" analysis. Instead, the instructions in agent.claude.md tell it to watch for these four trigger types during normal conversation. When one fires, the agent:

1. Finishes the current conversational turn (don't interrupt coaching to do file I/O)
2. Reads the current profile
3. Edits the relevant section
4. Optionally mentions the update to the user (for triggers 1 and 3 — explicit ones — always mention it; for trigger 2 — pattern detection — mention it when relevant to today's coaching)

---

## 3. Weekly Review Integration

The weekly review is the primary moment for profile consolidation. During the week, the profile gets spot updates from the triggers above. The weekly review is where the agent steps back and looks at the full picture.

### What Happens

The agent runs the weekly review as a scheduled check-in (Sunday evening or Monday morning — user preference stored in Decision Framework).

**Step 1: Load everything**
- Read `profiles/user.md`
- Call `get_summary(period="2026-W{n}")` for the week's outcome data
- Call `get_history(date_from=..., date_to=...)` for detailed records

**Step 2: Analyze patterns**
- Completion rate by goal type
- Days of the week that worked vs. didn't
- Reasons for skips/failures — are they recurring?
- Did the user's stated priorities match their actual behavior?

**Step 3: Update the profile**

The agent updates all three sections as needed:

- **Soul & Motivation:** Did any values become clearer or shift this week? ("User said career doesn't matter but spent 80% of effort on career goals — possible disconnect worth exploring")
- **Decision Framework:** Adjust rules based on what worked. ("Morning fitness works, evening fitness doesn't — schedule fitness before 9am." "User overcommits on Mondays — limit to one goal on Mondays.")
- **Patterns:** Add or refine observed tendencies. ("3rd week in a row with Wednesday skips." "Completion rate improves when goals are time-boxed.")

**Step 4: Adjust goals**
- If a monthly sub-goal is consistently failing, propose dropping or restructuring it
- If the user is ahead, propose stretching
- Adjust the upcoming week's plan based on updated framework

**Step 5: Share with the user**

The weekly review message is a short summary, not a report:

```
Weekly check-in:

This week: 8/10 daily goals completed.
- Fitness: 5/5 (strong)
- System design study: 2/4 (skipped Tue + Thu evenings)
- Writing: 1/1 (Sunday session worked well)

Pattern I noticed: evening study sessions don't stick.
I'm moving study to mornings next week.

Your March goal of finishing chapters 3-6 is on track
if we keep 3 sessions/week.

Anything you'd adjust?
```

The user can respond, and the agent incorporates feedback before finalizing the week's profile updates.

---

## 4. Profile Bootstrap

After onboarding, the profile looks like this. This is a realistic example for a software engineer focused on technical growth and health.

```markdown
# User Profile

## Soul & Motivation

Core drive: Wants to be genuinely excellent at software engineering, not just competent. Motivated by depth — understanding systems thoroughly, not surface-level familiarity.

Health is a close second. Has experienced burnout before and recognizes that physical health directly affects cognitive performance. Not training for competition — wants sustainable energy and longevity.

Values learning over credentials. Doesn't care about certifications; cares about being the person others come to with hard problems.

Tension to watch: tends to prioritize career over health when work gets intense. Has acknowledged this and wants to be called out on it.

## Decision Framework

Priority order: health >= career growth (explicitly stated — not "health when convenient")

Morning is peak productive time — use for hardest cognitive task (currently system design study).

Exercise works best early (before 8am) or at lunch. Evening workouts get skipped.

Work obligations are real but not priorities — distinguish "I have a deadline" from "I want to grow." Both get scheduled, but growth goals don't get dropped just because work is busy.

Weekends: one study session (Sunday morning), otherwise recovery. Don't over-schedule weekends.

## Patterns

[No patterns observed yet — will populate as data accumulates over the first 1-2 weeks.]
```

Note: the Patterns section starts empty. It's tempting to pre-fill it from onboarding conversation, but patterns should be evidence-based, not self-reported. The user might say "I'm a morning person" during onboarding (that goes in Decision Framework as a stated preference), but whether mornings actually produce better completion rates goes in Patterns after the data confirms it.

---

## 5. Instructions for agent.claude.md

The following is the exact text to add to the User Profile section of `config/agent.claude.md`. It replaces the current brief mention of profiles (lines 96-99).

```markdown
### User Profile

The user's profile lives at `profiles/user.md`. It is the most important file you maintain. It contains three sections: Soul & Motivation (what drives them), Decision Framework (rules for making priority calls), and Patterns (observed behavioral data).

**Reading the profile:**
- Read `profiles/user.md` at the start of EVERY session, before responding to anything.
- If the file doesn't exist, you are in onboarding. Create it after the onboarding conversation.
- Never make a recommendation without having read the profile first.

**Updating the profile — when to write:**

Update the profile when any of these happen during conversation:

1. **User states a value or priority.** ("Health matters more than career right now.") → Update Soul & Motivation and/or Decision Framework immediately.
2. **You notice a repeated pattern in outcomes.** (3+ skips on evening goals, consistently completes time-boxed tasks.) → Update Patterns during evening check-in or weekly review.
3. **User gives coaching feedback.** ("Don't check in so often." "I like morning suggestions.") → Update Decision Framework or Patterns immediately.
4. **User changes a goal.** (Drops, adds, or restructures a goal.) → Update Soul & Motivation if the "why" shifted, Decision Framework if priorities changed.

**How to write updates:**
- Read the current file first. Always.
- Edit only the relevant section. Don't rewrite the whole file.
- Keep entries concise — one line per insight, not paragraphs.
- For explicit updates (triggers 1 and 3): tell the user you've noted it. ("Noted — I'll prioritize health over career in future calls.")
- For observed patterns (trigger 2): mention it when it's relevant to today's coaching. Don't announce every pattern update.

**Weekly review and profile consolidation:**

During the weekly review (scheduled check-in, day/time stored in user's Decision Framework):

1. Read the full profile and this week's goal outcomes (`get_summary` + `get_history`).
2. Look for: completion patterns by goal type, by day of week, by time of day. Recurring skip reasons. Gaps between stated values and actual behavior.
3. Update all three profile sections based on the week's evidence:
   - Soul & Motivation: Did values clarify or shift?
   - Decision Framework: What scheduling/priority rules should change based on what worked?
   - Patterns: What trends are emerging or strengthening?
4. Summarize the week to the user in 5-8 lines. Highlight what worked, what didn't, and one adjustment you're making.
5. Let the user respond before finalizing. Incorporate their feedback.

**Profile bootstrap (onboarding):**

After the onboarding conversation, create `profiles/user.md` with:
- Soul & Motivation: populated from what the user shared about their goals and values
- Decision Framework: populated from stated preferences (schedule, priorities, constraints)
- Patterns: leave empty with a note "[No patterns observed yet]" — patterns come from data, not self-report

If the user says "I'm a morning person," that's a stated preference (Decision Framework). Whether mornings actually produce better results is a pattern (Patterns) — wait for evidence.
```

---

## Summary of Changes from Previous Report

| Aspect | Previous | Revised |
|---|---|---|
| Profile path | `profiles/{user_id}.md` | `profiles/user.md` |
| Learning triggers | Described conceptually | Concrete examples + mechanical "how the agent decides" |
| Weekly review | Not covered | Full design — load, analyze, update, summarize, get feedback |
| Profile bootstrap | Not covered | Realistic example with empty Patterns rationale |
| agent.claude.md text | Described what it should say | Actual copy-pasteable instructions |
| Complexity | Multi-user considerations | Single-user prototype simplifications |
