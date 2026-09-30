# Power BI Learnings: Row/Object-Level Security & Visualisation

## Row-Level Security (RLS)

- Filters which **rows** of data a user sees, via a DAX filter expression defined per role.
- **Static RLS**: fixed filter per role (e.g., `[Level3] <> "Team X"`). Simple exclusions/inclusions.
- **Dynamic RLS**: one role definition filters differently per user, via a user-mapping table and `USERPRINCIPALNAME()`/`USERNAME()` in the DAX filter. Scales to many users without one role per person.
- Configured in Power BI Desktop: **Modeling → Manage Roles**. Test with **View As**.
- Best practice: enforce RLS on **dimension tables**, not fact tables — relies on relationships to propagate the filter, avoiding `LOOKUPVALUE` where a relationship can do the same job.
- Map **security groups** (not individual users) to roles in the Power BI service — delegates membership management to admins.

### Dynamic RLS for hierarchies (parent-child pattern)
- Use `PATH(NodeID, ParentID)` as a calculated column on the org/hierarchy dimension to build each row's full lineage string.
- Use `PATHCONTAINS([Path], <assigned node ID>)` in the RLS filter — returns true for the assigned node *and every descendant*, so a user assigned at a higher level automatically sees all levels below.
- Common pattern for org-chart / manager-hierarchy dynamic RLS.
- Requires reshaping a flat multi-level table (Level 1...N columns) into a proper parent-child structure (`NodeID`, `ParentNodeID`) for `PATH()` to work.

### Recommended table design for hierarchical dynamic RLS
- `dim_Hierarchy`: one row per unique node — `NodeID` (surrogate key), `ParentNodeID`, flattened level columns (for slicers/display), `Path` (calculated).
- `dim_UserAccess` (bridge table): `UserEmail`, `AssignedNodeID` (FK), `AccessType`.
- Fact table(s) relate to `dim_Hierarchy` via `NodeID` (many-to-one) — RLS on the dimension propagates automatically.
- Keep separate fact tables for data that needs different OLS treatment (e.g., aggregated/summary data vs. raw free-text) so one can be hidden without affecting the other.

### Known limitations
- RLS can only filter **rows/values**, not restrict model objects (tables/columns/measures) — that's OLS's job.
- RLS on a slicer's source column restricts the slicer *and* every aggregate using that column together — you cannot have an unfiltered total include a value while blocking that value from being selected in the same column's slicer. Workaround: a **disconnected table** to populate the slicer (accepts user input without propagating filters to other tables), with measures using `SELECTEDVALUE`/`TREATAS` logic. Caveat: this is a **UI restriction, not a security restriction** — cross-filtering, drillthrough, "see records," export, or Q&A could still expose the excluded value, since the underlying rows aren't actually removed.
- Ragged/unbalanced hierarchies (branches of differing depth) are a **Matrix visual rendering limitation**, not an RLS limitation — no DAX filter fixes it. Only relevant if displaying the hierarchy as an expandable Matrix/tree, not for row filtering itself.

## Object-Level Security (OLS)

- Hides entire **tables or columns** from a role — not a row/value filter. Hidden objects don't appear in the field list, can't be added to visuals/slicers/filters, and can't be referenced in DAX or Q&A.
- Not DAX-based — it's a metadata permission (`None` = hidden, `Read` = visible) set per table/column, per role.
- Not configurable in Power BI Desktop natively — requires **Tabular Editor** (Roles dropdown → Table Permissions) or a **TMDL script** (`metadataPermission: none`) via the XMLA endpoint.
- Only applies to users with **read-only** access — Admins/Members/Contributors bypass OLS.
- A report visual using an OLS-hidden field breaks with no clear message for the restricted user — build a separate version of that visual/report for roles without access.

### RLS vs OLS — how to decide
- Need to hide specific **values within a column** (e.g., one category excluded, rest visible) → **RLS**.
- Need to remove **a whole field's filtering capability** (no demographic breakdown available at all, only an unsliced aggregate) → **OLS**, *if* the excluded state ("Total") isn't a literal stored row and is just the natural result of no filter being applied. RLS can't filter down to a value that doesn't exist as data.
- If the "Total" state **is** a literal stored row (e.g., banner/crosstab-style tables with an explicit "Total" member), RLS filtering to that row also works — but the field/slicer itself would remain visible with just one option, rather than disappearing.

### Combining RLS + OLS
- Both can be defined together in the **same role** — e.g., a role with an RLS filter for row scope and OLS table/column permissions for hiding a table.
- **Must be in the same role.** RLS and OLS cannot be combined across *different* roles — Microsoft's own guidance is explicit that this can introduce unintended access, and generates a query-time error for users belonging to such a role combination. One role per access tier, carrying both rule types.

## Implementation summary (from Desktop to Service)
1. **Modeling → Manage Roles** in Desktop: write DAX filter per role (RLS).
2. **Tabular Editor / TMDL**: set table/column metadata permission per role (OLS).
3. Publish to the Power BI service → dataset **Security** page → assign security groups to roles.
4. Use **View As** in Desktop to test each role before publishing.

## Visualisation formatting notes

### Making a single bar thicker / closer to the legend
- Controlled by **Inner padding** on the category axis (Y-axis for a horizontal bar chart; under Bars/Layout in the newer unified format pane).
- Reducing Inner padding % shrinks the empty space around the bar, making it thicker and pulling it closer to adjacent elements like the legend. 0% removes the gap entirely.
- Related: **Minimum category width** sets a pixel floor per category slot — useful when the number of categories varies via filters.

### Per-series data label colour (stacked bar/column)
- Format pane → **Data labels** → **Apply settings to** (or "Series") dropdown, defaults to "All."
- Switch it to a specific legend value to set that series' label colour/font independently — repeat per series for full per-segment control.
- Common use: white labels on dark segments, dark labels on light segments within the same stacked bar.
