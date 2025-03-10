# Gunicorn configuration file
import multiprocessing

# Server socket
bind = '0.0.0.0:5000'
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count()
worker_class = 'sync'
worker_connections = 1000
timeout = 120  # Увеличиваем таймаут до 120 секунд
keepalive = 2

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Process naming
proc_name = 'gunicorn_flask_app'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None

# Debugging
reload = True
reload_engine = 'auto'
spew = False
check_config = False

# Server hooks
def on_starting(server):
    pass

def on_reload(server):
    pass

def when_ready(server):
    pass

def on_exit(server):
    pass
