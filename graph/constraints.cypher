// Uniqueness constraints on every node ID (sync rule 5). Run before the first sync.
// Each node carries the same ID as its PostgreSQL row.
CREATE CONSTRAINT paper_id       IF NOT EXISTS FOR (n:Paper)       REQUIRE n.paper_id       IS UNIQUE;
CREATE CONSTRAINT author_id      IF NOT EXISTS FOR (n:Author)      REQUIRE n.author_id      IS UNIQUE;
CREATE CONSTRAINT institution_id IF NOT EXISTS FOR (n:Institution) REQUIRE n.institution_id IS UNIQUE;
CREATE CONSTRAINT venue_id       IF NOT EXISTS FOR (n:Venue)       REQUIRE n.venue_id       IS UNIQUE;
CREATE CONSTRAINT method_id      IF NOT EXISTS FOR (n:Method)      REQUIRE n.method_id      IS UNIQUE;
CREATE CONSTRAINT dataset_id     IF NOT EXISTS FOR (n:Dataset)     REQUIRE n.dataset_id     IS UNIQUE;
CREATE CONSTRAINT task_id        IF NOT EXISTS FOR (n:Task)        REQUIRE n.task_id        IS UNIQUE;
CREATE CONSTRAINT topic_id       IF NOT EXISTS FOR (n:Topic)       REQUIRE n.topic_id       IS UNIQUE;
CREATE CONSTRAINT setting_id     IF NOT EXISTS FOR (n:Setting)     REQUIRE n.setting_id     IS UNIQUE;
CREATE CONSTRAINT experiment_id  IF NOT EXISTS FOR (n:Experiment)  REQUIRE n.experiment_id  IS UNIQUE;
CREATE CONSTRAINT result_id      IF NOT EXISTS FOR (n:Result)      REQUIRE n.result_id      IS UNIQUE;
