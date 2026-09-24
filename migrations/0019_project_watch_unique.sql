PRAGMA foreign_keys = ON;

-- MVP invariant: one PROJECT watch per project. General watch types remain
-- unconstrained and are handled by the broader watch CRUD roadmap.
CREATE UNIQUE INDEX idx_watches_one_project_watch
  ON watches(project_id)
  WHERE watch_type = 'PROJECT' AND project_id IS NOT NULL;
