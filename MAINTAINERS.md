# Maintainers

This file says who maintains the project, what that means, and how to join.
It is deliberately short. The project is small enough that a page of shared
expectations does more good than a governance document.

## Current maintainers

| Name | GitHub | Role | Areas |
|------|--------|------|-------|
| Richard Atkinson | [@RichardAtCT](https://github.com/RichardAtCT) | Lead maintainer, releases | Everything; final say on security-sensitive changes |

Co-maintainers are listed here as they join. `CODEOWNERS` mirrors this table
so reviewers are requested automatically.

## What maintainers do

- **Respond within a week.** Every new issue and pull request gets a reply
  within seven days, even if the reply is "not now" or "needs more
  information". Silence is the one thing this project promises not to do.
- **Triage.** Apply labels, close duplicates, ask for missing details, and
  point contributors at the roadmap item or open PR that already covers
  their idea.
- **Review and merge.** Any maintainer may merge a pull request that has
  green CI, a first-pass bot review with no unresolved findings, and one
  approving human review. Changes under `src/security/`, `src/claude/`,
  `src/api/` and `.github/workflows/` need the lead maintainer's approval
  as well.
- **Release.** The lead maintainer cuts releases with `make bump-*`. Any
  maintainer may prepare the changelog and propose a release.

## Becoming a maintainer

The path is: contributor, then triager, then maintainer.

1. **Contributor.** Anyone with a merged pull request.
2. **Triager.** A contributor with three or more merged PRs, or sustained
   helpful activity on issues, can be given the GitHub *Triage* role on
   request or by invitation. Triagers label, close, and respond to issues
   and PRs but do not merge.
3. **Maintainer.** A triager who has been active for about three months and
   whose reviews the existing maintainers trust is invited to take *Write*
   access and is added to the table above and to `CODEOWNERS` for the areas
   they know.

Maintainers who have been inactive for six months are moved to an
"emeritus" line below, with thanks, and their access is reduced. They can
return at any time by asking.

## Decisions

Most decisions happen in the pull request or issue where they arise. When
maintainers disagree, the person who will do the work proposes, the others
comment within a week, and the lead maintainer decides if there is still no
agreement. Decisions that change the project's direction (a new major
version, dropping a feature area, adding a platform) are written down in an
issue labelled `decision` before work starts, so the reasoning survives.

## Labels

Maintainers keep this set current in the repository settings. Issue
templates apply the first two automatically.

| Label | Meaning |
|-------|---------|
| `needs-triage` | New, not yet looked at by a maintainer. Cleared weekly. |
| `bug`, `enhancement`, `question` | Type, set by the issue template. |
| `security` | Touches the security model. Lead maintainer review required. |
| `sdk` | Concerns the Claude Agent SDK integration or a version bump. |
| `good first issue` | Small, self-contained, and described well enough to start without asking. |
| `help wanted` | A maintainer wants this but will not get to it soon. |
| `blocked` | Waiting on an upstream change or another PR. Say which in a comment. |
| `decision` | A direction-setting discussion, see above. |
| `dependencies`, `ci` | Set by Dependabot. |

## Releases and support

- Minor releases roughly monthly while there is merged work to ship; patch
  releases whenever a fix warrants one.
- Semantic versioning. Behaviour is removed only in a major version, and
  only after a deprecation warning has shipped in at least one minor
  release before it.
- The previous major receives security fixes for six months after the next
  major ships.

## Emeritus

None yet.
