# Power BI Learnings

## Power Query (M) Basics

**Rename columns dynamically**
Build a config table (`From`/`To` columns) and use a helper function to rename by map:
```powerquery-m
fx_RenameByMap(tbl, renameCfg, optional ignoreMissing)
```
Merges old→new names, skips duplicates/missing columns gracefully (`Ignore` defaults true).

**Parse dates/versions from filenames**
Split filename on delimiters (`Text.Split`), extract tokens by index, wrap parsing in `try...otherwise null` to avoid errors on malformed input.

**Unix epoch timestamps (milliseconds)**
```powerquery-m
#datetime(1970,1,1,0,0,0) + #duration(0,0,0, [Column] / 1000)
```
Divide by 1000 since `#duration`'s third arg is seconds, not milliseconds. Check for timezone offset issues (epoch is UTC).

**Reorder columns without listing every column**
```powerquery-m
Table.ReorderColumns(
    PreviousStep,
    {"col1", "col2"} & List.RemoveItems(Table.ColumnNames(PreviousStep), {"col1", "col2"})
)
```
Scales to wide tables (100s of columns) — only name the ones you're repositioning.

**Numeric-to-label mapping (recode values)**
Avoid nested `Table.ReplaceValue` chains for numeric labels — `Replacer.ReplaceText` does substring matching, so replacing "1" first can corrupt "10", "11", "12". Use an exact-match lookup record instead:
```powerquery-m
Table.TransformColumns(
    tbl,
    {
        "ColumnName",
        each let
            m = [ #"1" = "Label A", #"2" = "Label B" ]
        in Record.FieldOrDefault(m, Text.From(_), _),
        type text
    }
)
```

**Unpivot + one-hot-encode multi-select/ranking questions**
For ranking columns (rank1/rank2/rank3 each holding an item ID), avoid `Table.Pivot` (can throw type-conversion errors). Use `List.Accumulate` to add one column per possible item value:
```powerquery-m
List.Accumulate(
    {1..11} & {97},
    Result,
    (state, itemValue) =>
        Table.AddColumn(
            state,
            "item_" & Text.From(itemValue),
            each if [rank1] = null and [rank2] = null and [rank3] = null then null
                 else if [rank1] = itemValue or [rank2] = itemValue or [rank3] = itemValue then 1 else 0,
            Int64.Type
        )
)
```
**Critical**: if all rank columns are null (respondent skipped the question), return `null`, not `0` — otherwise non-respondents get silently counted as "selected nothing" instead of excluded, inflating base sizes.

**Collapsing duplicate-label columns (avoid double-counting)**
When several source columns map to the same display label (e.g. multiple sub-items rolling up to one theme), group by `id + label` and take `List.Max` of the response flag — ensures a respondent who ticked any underlying item is counted once, not per matching column.

**En dash vs hyphen bugs**
Recoding text values via a lookup record is fragile if the record's keys use en dashes (–) instead of hyphens (-) — silent mismatch, values fall through to default. Always verify character-for-character when typing/pasting long value-mapping lists.

---

## DAX Measures

**Basic % calculation pattern**
```dax
DIVIDE(
    CALCULATE(COUNTROWS(fact), fact[ResponseValue] IN {4,5}),
    CALCULATE(COUNTROWS(fact))
)
```

**Filtered vs. Overall comparison ("vs benchmark" cards)**
```dax
VAR Filtered = [SomeMeasure]
VAR Overall = CALCULATE([SomeMeasure], ALL(dim_Table))
RETURN Filtered - Overall
```
**Gotcha**: `ALL(dim_Table)` strips *every* filter on that table, including ones you want to keep (e.g. year). Reapply with `VALUES()`:
```dax
CALCULATE([SomeMeasure], ALL(dim_Table), VALUES(dim_Table[Year]))
```

**Gotcha (bidirectional relationships)**: if a filter (e.g. a demographic slicer) lives on a *different* table than the one you're clearing with `ALL()`, and that table has a bidirectional relationship to your dimension table, you must also clear it explicitly:
```dax
CALCULATE([SomeMeasure], ALL(dim_Respondents), ALL(dim_OtherFilterTable), VALUES(dim_Respondents[Year]))
```
Otherwise "Overall" silently stays scoped to the demographic filter, producing wrong diffs.

**Rounding**: round once, at the final diff step — not on each intermediate value. Rounding both sides before subtracting loses precision (e.g. 91.79% vs 90.1% should round to +2, not +1).

**+/- sign formatting**
```dax
FORMAT(value, "+0;-0;0")
```
Returns text — cannot be plotted as a bar chart's numeric value. Keep two measures: a numeric one for charts/conditional formatting, a `FORMAT()`-wrapped one for cards/tables.
Note: Power BI's "Dynamic" format-string box (Modeling ribbon → Format dropdown) does **not** accept semicolon-delimited custom format codes — that only works via the model-level Custom Format property in older versions, or by wrapping in `FORMAT()` in the DAX itself.

**Suppressing small base sizes (n<5)**
```dax
IF([Base_size] < 5, BLANK(), <actual calculation>)
```
Returning `BLANK()` (not `0`) lets a chart naturally omit the data point.
**Critical gotcha**: if `Base_size` is evaluated *inside* a stacked bar chart with a Legend field, it can be evaluated per-legend-segment instead of for the whole category — incorrectly suppressing individual segments (e.g. "Disagree") even when the *whole question's* base size is fine. Fix:
```dax
Base_size = CALCULATE(DISTINCTCOUNT(fact[id]), ALLSELECTED())
```
`ALLSELECTED()` with no arguments clears whatever filter context the visual itself contributes (axis, legend) while still respecting slicers/RLS — restoring a whole-category check instead of a per-segment one.

**Keeping zero-value legend segments visible**
A measure returning `BLANK()` when a category has zero matching rows causes that legend entry to disappear from stacked/pie charts. Force a real `0`:
```dax
DIVIDE(numerator, denominator, 0)   -- third arg = alternate result on blank/divide-by-zero
```
or for implicit `COUNT()`:
```dax
COUNT(fact[Column]) + 0   -- BLANK() + 0 = 0
```

**Company-wide benchmark tables (for RLS-safe comparisons)**
Row-level security correctly restricts what a user sees, but `ALL()` inside a measure **cannot bypass RLS** — a restricted manager's "Overall" will still only reflect their own RLS-visible rows, not the true company-wide figure.
To show a genuine unrestricted benchmark to RLS-restricted users, pre-aggregate it in Power Query as its own table (no RLS applied to that table at all):
```powerquery-m
let
    Source = fact_Table,
    FilteredYear = Table.SelectRows(Source, each [year] = 2026),
    Grouped = Table.Group(FilteredYear, {"QuestionCode"}, {
        {"TotalCount", each Table.RowCount(_), Int64.Type},
        {"AgreeCount", each Table.RowCount(Table.SelectRows(_, each [ResponseValue] >= 4)), Int64.Type}
    }),
    AddPct = Table.AddColumn(Grouped, "%_Agree_Overall", each [AgreeCount] / [TotalCount], type number)
in
    AddPct
```
Then reference it via `LOOKUPVALUE` instead of `CALCULATE(..., ALL(...))`:
```dax
VAR Overall = LOOKUPVALUE(dim_Benchmark[%_Agree_Overall], dim_Benchmark[QuestionCode], SELECTEDVALUE(fact[QuestionCode])) * 100
```
Build one benchmark table per distinct metric type (scale %, NPS, multi-response %, dimension %) since each is keyed/calculated differently — a single flat table mixing metric types requires an extra `MetricType` discriminator column and is more complex than several small dedicated tables.

**Duplicate-key safety in LOOKUPVALUE**
`LOOKUPVALUE` errors if more than one row matches. If the lookup table might have duplicate keys, use instead:
```dax
CALCULATE(
    COUNTROWS(FILTER(tbl, tbl[Key] = SomeValue && tbl[Flag] = "Yes")),
) > 0
```

**TREATAS for virtual (relationship-free) filtering**
When a mapping table has a many-to-many relationship to a fact table (e.g. one metric belongs to multiple categories), avoid building an actual M:M relationship (fan-out/double-counting risk, and forces per-category expansion). Instead keep the mapping table fully disconnected and filter virtually:
```dax
VAR MatchingKeys = CALCULATETABLE(VALUES(dim_Map[Key]), dim_Map[Category] = Selected, dim_Map[Sentiment] = "Positive")
VAR Count = CALCULATE(COUNTROWS(fact), TREATAS(MatchingKeys, fact[Key]))
```
Put category/sentiment fields from the disconnected table on Axis/Legend; `SELECTEDVALUE()` reads what's selected, `TREATAS()` applies the filter without any stored relationship.

**Custom per-question "positive" definitions**
Some scales are reverse-coded (e.g. a frequency scale where low values are actually positive) or only have 4 options instead of 5 (no neutral). Handle per-question logic with `SWITCH(TRUE(), ...)`:
```dax
SWITCH(
    TRUE(),
    SelectedQ = "SpecialQuestion", fact[ResponseValue] IN {1,2},
    fact[ResponseValue] IN {4,5}   -- default
)
```
**Gotcha**: `IN` cannot take a `VAR` holding a dynamically-chosen list as its right-hand side — DAX needs a literal set. Put the `SWITCH` directly inside `CALCULATE`'s filter argument (returning a boolean condition) rather than trying to assign the list to a variable first.

**"Show N/A for one measure differs from another on the same card" bug**
If a chart shows one number but its conditional-formatting color uses a *different, similarly-named* measure, check the formatting dialog's "base this on" field is actually pointing at the same measure the card displays — easy to mismatch after copy-pasting cards.

---

## Common Root Causes of "wrong number everywhere" Bugs

1. **Implicit aggregation** — dragging a raw column (not a measure) onto Values defaults to `Count of X` / `Sum of X`, which is rarely intended. Always use an explicit measure.
2. **SELECTEDVALUE returning BLANK()** — happens when the visual's context doesn't uniquely determine one category (e.g. multiple QuestionCodes in view at once, or a Legend/Axis field not actually related to the fact table). A `LOOKUPVALUE` keyed on a blank value fails silently.
3. **Broken/missing relationship** — a category field with no active relationship to the fact table won't filter anything; every row of a chart will show the same (unfiltered) result.
4. **Copy-pasted visual retaining stale field bindings** — sometimes rebuilding a chart from scratch resolves bugs that persist despite the fields looking correct in an existing/copied visual.

---

## Row-Level Security (RLS)

**Basic dynamic role**
```dax
[UserPrincipalName] = USERPRINCIPALNAME()
```
Test with **Modeling → View as → "Other user"** (type a specific email to simulate) — not by hardcoding the email into the rule itself.

**RLS only restricts Viewer-level access**
RLS does **not** apply to users with Workspace Admin, Member, or Contributor roles — even if they only intend to view the report. Restricted users must be added as Viewers (or access via a published App), or RLS is silently bypassed.

**RLS restricting one table doesn't cascade automatically**
Applying RLS only to a security-mapping table (listing which user sees which team/scope) has **no effect** on any other table unless a relationship exists connecting it to your fact/dimension tables. RLS propagates through active relationships only, in the direction they allow filtering.

**One-to-many relationship direction matters**
A standard one-to-many relationship only filters from the "one" side to the "many" side. If RLS is applied on the "many" side (e.g. a bridge table) and needs to restrict something upstream, the relevant relationship must be set to **bidirectional**, or the filter won't propagate backward.
Bidirectional relationships carry real trade-offs: ambiguous filter paths, potential performance cost, and unintended cross-filtering between unrelated visuals sharing the same tables. Test all existing RLS rules again after making a relationship bidirectional.

**Column-level (not just row-level) restriction has no dynamic native equivalent**
If certain columns on a shared table need to be hidden for some users but not others (not just certain rows), Object-Level Security (OLS) exists but is **static per role**, not dynamic per user via `USERPRINCIPALNAME()`. The practical workaround is restructuring the report so restricted fields are sourced from a separate table that RLS *can* dynamically restrict, rather than pulling those fields from a shared table directly.

**Verifying which UserPrincipalName format to use**
Some users' actual Entra UPN differs from their plain email — confirm via Power BI Admin portal → Users → search email → check "User principal name" field on their Guest profile, and use that exact string in your security-mapping table if it differs from their plain email address.

---

## Visual-Level Behavior & Formatting

**Hiding a whole visual conditionally — no fully native method exists**
Confirmed (per Microsoft Community support) there is no built-in way to conditionally hide/show an entire visual based on a measure. Two real options:
1. **Visual-level filter** (Filters pane) using a calculated column (not always a measure — measures can behave inconsistently across visual types for this purpose) set to "is 1"/"is 0". Works reliably on bar charts; less reliably on pie charts and cards in some cases.
2. **Masking overlay** — place a solid-fill Card (or Shape) exactly over the target visual, filtered/conditionally-formatted to appear only when the suppression condition is true, sitting above the target in z-order (Selection pane). This is the only approach confirmed to work universally across chart types, including pie charts.
   - A Shape has **no Filters pane at all** — cannot be filtered by a field like QuestionCode. Use a Card instead if per-category filtering is needed.
   - Conditional formatting on a Card's Fill/Background **cannot produce true transparency** — it can only switch between solid opaque colors. Matching the color to the report's background approximates invisibility only when nothing else is meant to show through; it will still visually block content behind it.
   - To make a masking Card properly disappear (revealing the chart underneath) rather than just recolor, use a genuine visual-level filter (calculated column, "is 0") rather than color-matching.

**"Count of X" filter cards behaving oddly / unresponsive**
If a numeric flag column (e.g. 0/1) is dragged into Filters and auto-summarizes as "Count of X", Basic filtering's checkbox list no longer shows the raw 0/1 values — it shows a distinct-count aggregate instead, which can make the filter card appear broken/unresponsive. Fix: remove the field, set its "Summarize by" to **None** in Model view (Properties pane) so future drags default to raw values, or fix the aggregation dropdown before it gets "stuck".

**Legend showing duplicate category names inconsistently colored/ordered**
If the same label text (e.g. "Neutral") is shared across multiple different underlying scales, Power BI cannot apply one consistent Sort-by-Column value to it — each occurrence may need a different sort position depending on which scale it belongs to. Fix: build a **compound key** column (`ScaleType & "|" & ResponseLabel`) for sorting purposes, but continue displaying the plain label. Set Sort-by-Column on the display field pointing to a sort-value column keyed by the compound logic, computed via a lookup record in Power Query.
For coloring, similarly, apply Data Colors `fx` conditional formatting matched on the plain label (not scale-specific) if color should be consistent regardless of source scale — different from the sort problem, which does require scale-awareness.

**Table/Matrix visuals**
- Conditional formatting: right-click the column header → Conditional formatting, or use Format pane → Cell elements (not the same location as Card conditional formatting).
- Column/Row header show/hide toggle may not exist in all versions — fallback is setting header font color to match background and minimizing font size.
- Resizing issues (only the outer selection border moves, content doesn't) are often caused by visual grouping — check the Selection pane, right-click → Ungroup if applicable, or check "Group" is greyed out to rule this out.
- Row height has no direct control — increasing Values font size is the practical lever, since rows auto-expand to fit text.

**Top N filtering**
Only available for **measures** on Filters (not raw columns): drag a measure into "Filters on this visual" → Filter type: **Top N** → specify N → "By value" set to a ranking measure.

**Sort by another column — requires strict 1:1 uniqueness**
"Cannot sort column A by column B" occurs when column B has more than one distinct value for any single value in column A. This applies even across the whole table (not scoped per visual) — if a duplicate value exists anywhere (e.g. "Other" repeated across categories with different sort numbers), you must either make column A values unique or give them all one consistent sort value.

**Diagonal/positional stability of a value across filter changes**
A bar chart data label's position always shifts with bar length as filters change. To show a number in a genuinely fixed position that stays aligned to categories regardless of filtering, a **Table** (not Card) is the only visual guaranteeing one row per category — Cards can vanish/misalign when a value is blank/zero. Charts (bar/gauge) inherently can't decouple a label's screen position from its underlying data value.

**Theme JSON for bulk font changes**
```json
{
  "name": "Custom",
  "textClasses": {
    "label": {"fontFace": "Lato, 'Segoe UI'", "fontSize": 10},
    "callout": {"fontFace": "Lato, 'Segoe UI'", "fontSize": 32}
  }
}
```
Apply via View → Themes → Browse for themes. Only affects visuals still using theme defaults — manually-overridden fonts on individual visuals are untouched.

---

## Publishing / Renaming

- Rename a published report/dataset via the **Power BI Service** (Workspace → "..." → Rename), not by renaming the local .pbix file. This preserves the underlying IDs so republishing the same .pbix updates the existing report rather than creating a duplicate.
- The SharePoint file name and the Service's report name are independent — renaming one doesn't require renaming the other.
- Sharing a report/dashboard link also grants access to its underlying semantic model by default — RLS/OLS must be explicitly configured, or all report viewers see identical, unrestricted data despite having "different permission types" nominally assigned.
