# Phase96 NASA Body Extraction Repair Preview

- quality_verdict: `nasa_body_extraction_blocked_needs_better_raw`
- production_ready: `False`
- live_fetch_used: `False`
- candidate_count: 17
- accepted_reviewable: 0
- rejected_search_or_nav: 16
- rejected_boilerplate: 0
- failed: 1
- needs_live_refetch: `True`

Root cause: existing NASA evaluation previews are dominated by navigation/search/recent-news chrome.
Next: re-sample NASA with better body extraction or provide richer existing raw; no shadow apply preflight yet.

Rejected examples:
- `rejected_search_or_nav` `NASA Space Science Data Coordinated Archive Status` https://nssdc.gsfc.nasa.gov/planetary/factsheet - no_non_navigation_body_in_existing_preview
- `rejected_search_or_nav` `Solar System Exploration` https://science.nasa.gov/solar-system - no_non_navigation_body_in_existing_preview
- `rejected_search_or_nav` `About the Planets` https://science.nasa.gov/solar-system/planets - no_non_navigation_body_in_existing_preview
- `rejected_search_or_nav` `Moons` https://science.nasa.gov/solar-system/moons - no_non_navigation_body_in_existing_preview
- `rejected_search_or_nav` `Asteroids` https://science.nasa.gov/solar-system/asteroids - no_non_navigation_body_in_existing_preview
- `rejected_search_or_nav` `Comets` https://science.nasa.gov/solar-system/comets - no_non_navigation_body_in_existing_preview
- `rejected_search_or_nav` `Science Missions - NASA Science` https://science.nasa.gov/mission - no_non_navigation_body_in_existing_preview
- `rejected_search_or_nav` `Juno - NASA Science` https://science.nasa.gov/mission/juno - no_non_navigation_body_in_existing_preview
