# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Context

This is the `calendars` Django app within the larger **bkmonitor** (BlueKing Monitor) project. See the parent `CODEBUDDY.md` at the repository root for project-wide commands, architecture, and conventions (Python 3.11, Django 4.2, `uv`, `core.drf_resource`, role-based configuration, etc.).

## Testing

The `calendars` test directory is not listed in `pyproject.toml` `testpaths`, so run tests explicitly:

```bash
# Run all calendars tests
pytest calendars/tests/

# Run a specific test file
pytest calendars/tests/item.py
pytest calendars/tests/calendar.py

# Run a specific test class or method
pytest calendars/tests/item.py::TestItem
pytest calendars/tests/item.py::TestItem::test_edit_item

# Via Django manage.py
python manage.py test calendars.tests
```

Tests use `pytest.mark.django_db(databases="__all__")` and rely on the `mocker` fixture from `pytest-mock`.

## App Architecture

The calendars app provides on-call calendar management for alert suppression. It supports creating calendars with time-based items that can repeat (daily, weekly, monthly, yearly) and handles time zones.

### Models

- **`CalendarModel`** (`models.py`): Represents a calendar. Fields include `name`, `classify` (`"default"` for built-in, `"custom"` for user-created), `deep_color`, `light_color`, and `bk_tenant_id` for multi-tenancy. Built-in calendars (e.g., "weekend") cannot be modified by users.
- **`CalendarItemModel`** (`models.py`): Represents a calendar event/item. Fields include `name`, `calendar_id`, `start_time`, `end_time` (Unix timestamps), `repeat` (JSON dict), `parent_id`, `time_zone`, and `bk_tenant_id`.

Both models extend `AbstractModel` which auto-sets `create_user`, `create_time`, `update_user`, and `update_time` on save.

### Repeat Configuration (`repeat` JSON field)

The `repeat` dict controls recurrence:

| Key | Type | Description |
|-----|------|-------------|
| `freq` | str | `"day"`, `"week"`, `"month"`, `"year"` |
| `interval` | int | Repeat interval (e.g., every 2 weeks) |
| `until` | int / null | End timestamp; `null` means never ends |
| `every` | list[int] | For `week`: 0-6 (0=Sunday); for `month`: 1-31; for `year`: 1-12; for `day`: `[]` |
| `exclude_date` | list[int] | Dates (day-start timestamps) to skip |

On save, if `every` is empty and `freq` is not `day`, the model auto-populates `every` from `start_time` (weekday, day, or month).

### Edit/Delete Semantics for Repeating Items

The app supports three edit/delete scopes (defined in `constants.py`):

- **ALL (0)**: Modify/delete the entire repeating series. Deleting also removes child items (`parent_id` matches).
- **CURRENT (1)**: Modify/delete only the selected occurrence. Adds the date to `exclude_date` on the parent; for edits, creates a new non-repeating child item with `parent_id` set.
- **CURRENT_AND_FUTURE (2)**: Modify/delete from the selected occurrence forward. Creates a new independent item for the future, sets the original's `until` to just before the selected date, detaches future child items, and cleans up `exclude_date`.

### API Layer

The app uses `core.drf_resource`:

- **`views.py`**: `CalendarsViewSet` (a `ResourceViewSet`) exposes all endpoints via `ResourceRoute` mappings. Read actions and `item_detail`/`item_list` are public; write actions require `ActionEnum.MANAGE_CALENDAR` permission.
- **`resources/calendar.py`**: Resources for calendar CRUD (`SaveCalendarResource`, `EditCalendarResource`, `GetCalendarResource`, `ListCalendarResource`, `DeleteCalendarResource`).
- **`resources/item.py`**: Resources for item CRUD and queries (`SaveItemResource`, `EditItemResource`, `DeleteItemResource`, `ItemListResource`, `ItemDetailResource`, `GetParentItemListResource`, `GetTimeZoneResource`).
- **`urls.py`**: Registers `CalendarsViewSet` via `ResourceRouter`.

### Time Zone Handling

- Items store `time_zone` (default `Asia/Shanghai`).
- `get_offset(time_zone)` computes the UTC offset in hours.
- `timestamp_to_tz_datetime` and `datetime_to_tz_timestamp` in `bkmonitor.utils.time_tools` convert between timestamps and localized datetimes.
- `TIME_ZONE_DICT` in `constants.py` maps localized display names to IANA time zone names.

### Query Logic (`ItemListResource`)

`ItemListResource` expands repeating items into concrete occurrences within a query range:

1. Iterates over all matching `CalendarItemModel` records.
2. For non-repeating items, includes them if they overlap the query range.
3. For repeating items, iterates from `start_time` to `min(end_time, until)` using `find_next_start_time`, which handles day/week/month/year arithmetic.
4. Skips dates in `exclude_date`.
5. Returns a list grouped by day: `[{"today": timestamp, "list": [...]}, ...]` sorted chronologically.

Key helper functions in `resources/item.py`:
- `find_time_by_week`, `find_time_by_month`, `find_time_by_year`: Compute the next occurrence for the respective frequency.
- `get_day`: Normalizes a datetime to a day-start or day-end timestamp.

### Database

- Tables: `calendar`, `calendar_item`.
- Routed to the `monitor_api` database per `bkmonitor/db_routers.py`.
- Migrations include default data seeding (e.g., a "weekend" calendar).
