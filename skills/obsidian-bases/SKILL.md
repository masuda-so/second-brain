---
name: obsidian-bases
description: Create and edit Obsidian Bases (.base files) with views, filters, formulas, and summaries. Use when working with .base files, creating database-like views of notes, or when the user mentions Bases, table views, card views, filters, or formulas in Obsidian.
---

# Obsidian Bases Skill

> Third-party attribution: This content includes material derived from
> kepano/obsidian-skills. See THIRD_PARTY_NOTICES.md.

## Workflow

1. Create a `.base` file in the vault with valid YAML content
2. Add `filters` to select which notes appear (by tag, folder, property, or date)
3. Add `formulas` (optional): define computed properties
4. Configure `views`: add one or more views (`table`, `cards`, `list`, or `map`)
5. Validate: verify valid YAML and all referenced properties/formulas exist
6. Open in Obsidian to confirm the view renders correctly

## Schema

```yaml
# Global filters apply to ALL views
filters:
  and: []
  or: []
  not: []

# Computed properties usable across all views
formulas:
  formula_name: 'expression'

# Display name overrides for properties
properties:
  property_name:
    displayName: "Display Name"
  formula.formula_name:
    displayName: "Formula Display Name"

# Custom summary formulas
summaries:
  custom_summary_name: 'values.mean().round(3)'

# One or more views
views:
  - type: table | cards | list | map
    name: "View Name"
    limit: 10
    groupBy:
      property: property_name
      direction: ASC | DESC
    filters:
      and: []
    order:
      - file.name
      - property_name
      - formula.formula_name
    summaries:
      property_name: Average
```

## Filter Syntax

```yaml
# Single filter
filters: 'status == "done"'

# AND — all conditions must be true
filters:
  and:
    - 'status == "done"'
    - 'priority > 3'

# OR — any condition can be true
filters:
  or:
    - file.hasTag("book")
    - file.hasTag("article")

# NOT — exclude matching items
filters:
  not:
    - file.hasTag("archived")

# Nested
filters:
  or:
    - file.hasTag("tag")
    - and:
        - file.hasTag("book")
        - file.hasLink("Textbook")
```

### Filter Operators

`==`, `!=`, `>`, `<`, `>=`, `<=`, `&&`, `||`, `!`

## File Properties Reference

| Property | Type | Description |
|----------|------|-------------|
| `file.name` | String | File name |
| `file.basename` | String | File name without extension |
| `file.path` | String | Full path |
| `file.folder` | String | Parent folder path |
| `file.size` | Number | File size in bytes |
| `file.ctime` | Date | Created time |
| `file.mtime` | Date | Modified time |
| `file.tags` | List | All tags |
| `file.links` | List | Internal links |
| `file.backlinks` | List | Backlinks |

## Formula Syntax

```yaml
formulas:
  # Arithmetic
  total: "price * quantity"

  # Conditional
  status_icon: 'if(done, "done", "pending")'

  # Date formatting
  created: 'file.ctime.format("YYYY-MM-DD")'

  # Days since created (Duration → number via .days)
  days_old: '(now() - file.ctime).days'

  # Days until due (guard null with if())
  days_until_due: 'if(due_date, (date(due_date) - today()).days, "")'
```

**Duration pitfall**: Subtracting two dates returns a Duration type. Always access `.days`, `.hours`, etc. before calling number functions.

```yaml
# CORRECT
"(now() - file.ctime).days.round(0)"

# WRONG — Duration does not support .round() directly
"(now() - file.ctime).round(0)"
```

## Key Functions

| Function | Description |
|----------|-------------|
| `date(string)` | Parse string to date |
| `now()` | Current date and time |
| `today()` | Current date |
| `if(cond, t, f?)` | Conditional |
| `duration(string)` | Parse duration string |
| `file(path)` | Get file object |
| `link(path, display?)` | Create a link |

## Default Summary Formulas

`Average`, `Min`, `Max`, `Sum`, `Range`, `Median`, `Stddev`,
`Earliest`, `Latest`, `Checked`, `Unchecked`, `Empty`, `Filled`, `Unique`

## Complete Examples

### Projects Tracker

```yaml
filters:
  and:
    - 'type == "project"'
    - file.inFolder("Projects")

formulas:
  days_until_review: 'if(review, (date(review) - today()).days, "")'
  overdue: 'if(review, date(review) < today() && status != "completed", false)'

properties:
  formula.days_until_review:
    displayName: "Days to Review"

views:
  - type: table
    name: Active
    filters:
      and:
        - 'status == "active"'
    order:
      - file.name
      - status
      - review
      - formula.days_until_review
    groupBy:
      property: status
      direction: ASC

  - type: table
    name: All
    order:
      - file.name
      - status
      - review
```

### Daily Journal Index

```yaml
filters:
  and:
    - file.inFolder("Daily")
    - 'type == "daily"'

formulas:
  day_of_week: 'date(file.basename).format("dddd")'

views:
  - type: table
    name: Recent
    limit: 30
    order:
      - file.name
      - formula.day_of_week
      - file.mtime
```

### Books Reading List

```yaml
filters:
  or:
    - file.hasTag("book")

formulas:
  status_icon: 'if(status == "reading", "reading", if(status == "done", "done", "to-read"))'

views:
  - type: cards
    name: Library
    order:
      - file.name
      - author
      - formula.status_icon
```

## Embedding Bases

```markdown
![[MyBase.base]]

<!-- Specific view -->
![[MyBase.base#View Name]]
```

## YAML Quoting Rules

- Use single quotes for formulas containing double quotes: `'if(done, "Yes", "No")'`
- Strings containing `:`, `{`, `}`, `[`, `]` must be quoted

## Troubleshooting

**Duration math error**: Subtracting dates returns Duration, not number. Use `.days`, `.hours`, etc.

**Missing null check**: Use `if()` to guard properties that may not exist on all notes.

**Referencing undefined formula**: Every `formula.X` in `order` must have a matching entry in `formulas`.

## References

- [Bases Syntax](https://help.obsidian.md/bases/syntax)
- [Functions](https://help.obsidian.md/bases/functions)
- [Views](https://help.obsidian.md/bases/views)
