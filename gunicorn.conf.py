# Gunicorn reads this file automatically at startup (no command-line flags
# needed), so these apply even when the start command can't be edited — e.g. a
# Blueprint-managed Render service.
#
# The AI requests (plan, meeting, portfolio, chat) take ~40-60 seconds. Gunicorn's
# default worker timeout is 30s, which kills them mid-request and surfaces as
# "Something went wrong" on the live site. Raise it well past the AI call length.
timeout = 180        # seconds
threads = 4          # keep the site responsive during a long AI call
workers = 1          # the free tier has limited memory
