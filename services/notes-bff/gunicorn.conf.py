from oc_logging.ecs import ecs_logconfig

from notes_bff.main import SERVICE

logconfig_dict = ecs_logconfig(SERVICE)

# Prometheus metrics live in process memory, so one worker per pod; scale with threads and replicas.
workers = 1
threads = 8
