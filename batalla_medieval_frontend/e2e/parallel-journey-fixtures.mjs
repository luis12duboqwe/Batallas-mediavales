// Prepare only an additional open world in an already-migrated disposable E2E database.
// Canonical seed and G2/G7/G8/G9/G10 fixtures are supplied by the repository.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertIsolated } from './parallel-journey-helpers.mjs';

assertIsolated();
const python = `
from app import models
from app.database import SessionLocal
db=SessionLocal()
try:
    existing=db.query(models.World).filter_by(name="Parallel Journey World B").one_or_none()
    if existing is None:
        existing=models.World(name="Parallel Journey World B", speed_modifier=1.0, resource_modifier=1.0, map_size=64, special_rules="Isolated cross-world QA fixture", lifecycle_status="open", is_active=True)
        db.add(existing)
    db.commit()
    db.refresh(existing)
    print("PARALLEL_JOURNEY_WORLD_B="+str(existing.id))
finally:
    db.close()
`;
const output = execFileSync(process.env.PARALLEL_JOURNEY_PYTHON || 'python3', ['-c', python], {
  encoding: 'utf8', timeout: 15000,
  env: { ...process.env, PYTHONPATH: resolve(dirname(fileURLToPath(import.meta.url)), '../../batalla_medieval_backend') },
});
console.log(output.trim());
