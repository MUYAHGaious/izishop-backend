"""
Gunicorn configuration for IziShop Backend
Production-ready settings for FastAPI
"""
import multiprocessing
import os

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
# Formula: (2 x $num_cores) + 1
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# Worker lifecycle
max_requests = 1000
max_requests_jitter = 50
timeout = 30
graceful_timeout = 30
keepalive = 2

# Logging
accesslog = "/var/www/izishopin.com/logs/gunicorn_access.log"
errorlog = "/var/www/izishopin.com/logs/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "izishop_backend"

# Server mechanics
daemon = False
pidfile = "/var/run/gunicorn_izishop.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (handled by Nginx)
keyfile = None
certfile = None

# Preload app for faster worker spawn
preload_app = True

# Forwarded allow ips (trust Nginx)
forwarded_allow_ips = "127.0.0.1"
