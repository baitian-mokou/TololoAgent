# NASA shadow source readiness / query preview

Phase 47 reads the local `data/triples_shadow/nasa` artifact produced by the guarded Phase 46 apply.
It does not import into the default triples tree, Chroma, or Neo4j.

- ready: `True`
- blocked_reason: ``
- active_source: `zh_wikipedia`
- default_source_unchanged: `True`
- formal_default_triples_write: `False`
- chroma_write: `False`
- neo4j_write: `False`

## Counts

| items | triples | narratives |
| ---: | ---: | ---: |
| 48 | 192 | 192 |

## Sample Query Preview

### subject: `NASA Space Science Data Coordinated Archive Status`

- result_count: `4`
- `NASA Space Science Data Coordinated Archive Status` `SOURCE_URL` `https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html`
- `NASA Space Science Data Coordinated Archive Status` `HAS_TOPIC` `asteroid`
- `NASA Space Science Data Coordinated Archive Status` `INSTANCE_OF` `asteroid`

### subject: `Planetary Defense at NASA`

- result_count: `4`
- `Planetary Defense at NASA` `SOURCE_URL` `https://science.nasa.gov/planetary-defense/`
- `Planetary Defense at NASA` `HAS_TOPIC` `asteroid`
- `Planetary Defense at NASA` `INSTANCE_OF` `asteroid`

### subject: `Bennu`

- result_count: `4`
- `Bennu` `SOURCE_URL` `https://science.nasa.gov/solar-system/asteroids/101955-bennu/`
- `Bennu` `HAS_TOPIC` `asteroid`
- `Bennu` `INSTANCE_OF` `asteroid`

### relation: `SOURCE_URL`

- result_count: `5`
- `NASA Space Science Data Coordinated Archive Status` `SOURCE_URL` `https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html`
- `Planetary Defense at NASA` `SOURCE_URL` `https://science.nasa.gov/planetary-defense/`
- `Bennu` `SOURCE_URL` `https://science.nasa.gov/solar-system/asteroids/101955-bennu/`

### relation: `HAS_TOPIC`

- result_count: `5`
- `NASA Space Science Data Coordinated Archive Status` `HAS_TOPIC` `asteroid`
- `Planetary Defense at NASA` `HAS_TOPIC` `asteroid`
- `Bennu` `HAS_TOPIC` `asteroid`

### relation: `INSTANCE_OF`

- result_count: `5`
- `NASA Space Science Data Coordinated Archive Status` `INSTANCE_OF` `asteroid`
- `NASA Space Science Data Coordinated Archive Status` `INSTANCE_OF` `small body`
- `Planetary Defense at NASA` `INSTANCE_OF` `asteroid`

### topic: `asteroid`

- result_count: `5`
- `NASA Space Science Data Coordinated Archive Status` `SOURCE_URL` `https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html`
- `NASA Space Science Data Coordinated Archive Status` `HAS_TOPIC` `asteroid`
- `NASA Space Science Data Coordinated Archive Status` `INSTANCE_OF` `asteroid`

### topic: `comet`

- result_count: `5`
- `Comet 103P/Hartley (Hartley 2)` `SOURCE_URL` `https://science.nasa.gov/solar-system/comets/103p-hartley-hartley-2/`
- `Comet 103P/Hartley (Hartley 2)` `HAS_TOPIC` `comet`
- `Comet 103P/Hartley (Hartley 2)` `INSTANCE_OF` `comet`

### narrative: `NASA Space Science Data Coordinated Archive Status`

- result_count: `3`
- `NASA Space Science Data Coordinated Archive Status - NASA`: Explore Search News & Events News & Events News Releases Recently Published Video Series on NASA+ Podcasts & Audio Blogs
- `NASA Space Science Data Coordinated Archive Status - NASA`: n read What’s Up: July 2026 Skywatching Tips from NASA article 3 weeks ago Back Missions Search All NASA Missions A to Z
- `NASA Space Science Data Coordinated Archive Status - NASA`: etary Science Astrophysics & Space Science The Sun & Heliophysics Biological & Physical Sciences Lunar Science Citizen S

### narrative: `Planetary Defense at NASA`

- result_count: `3`
- `Planetary Defense at NASA - NASA Science Facebook logo Instagram logo Linkedin logo`: Explore Search News & Events News & Events Recently Published Video Series on NASA+ Podcasts & Audio Blogs Newsletters S
- `Planetary Defense at NASA - NASA Science Facebook logo Instagram logo Linkedin logo`: ago Back Missions Search All NASA Missions A to Z List of Missions Upcoming Launches and Landings Spaceships and Rockets
- `Planetary Defense at NASA - NASA Science Facebook logo Instagram logo Linkedin logo`: ogical & Physical Sciences Lunar Science Citizen Science Astromaterials Aeronautics Research Human Space Travel Research
