## Commit conventions

- Format: `<type>(<scope>): <subject>`, e.g. `feat(auth): add login endpoint`
- type: feat / fix / refactor / chore / docs / test / perf

## Frontend conventions

### Toast (bottom capsule)

- The `.toast-container` handles horizontal centering (`left: 50%` + `translateX(-50%)`). Capsules are laid out inside the container; entrance animation must only use vertical translate / opacity — **never** apply a `translateX` to a capsule that omits the horizontal centering.
- **Never** redefine same-name `@keyframes toast-in` / `toast-out` in late-loaded styles (it overrides the global definition; the first frame sits off-center then snaps back).
- Semantic color goes only through the 4px left color bar: error red, warning orange, success green, info blue. Chrome (cards / buttons / nav) must not reuse this left edge line.

### Decoration & emphasis

- Cards, buttons, and nav must **not** use a left brand-color vertical bar (`::before` / inset left edge / glass `::after` vertical highlight) to indicate selected / active / pinned state.
- Pinned items use a top-right pin icon; nav active state uses background and text color.
- A blockquote's left border belongs to content typography, not Chrome.

### Notes list

- Card view must stay equal-height at a given density (`--notes-card-h` + `overflow: hidden`); do not let cells stretch with summary length.
- Loose / compact density transitions via CSS variables; the main column keeps `scrollbar-gutter: stable` to avoid scrollbar flashes or grid jumps when switching.
- The batch action bar enters / exits by animating height + opacity; never insert the whole bar instantly.

### Dangerous actions

- `.is-danger` must override the generic button `color` in the dark theme; use `var(--error)`.
