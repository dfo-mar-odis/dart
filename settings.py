import os

INSTALLED_APPS = [
    "dynamic_db_router",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST"),
        "PORT": "5432",
    },
    "oracle": {
        "ENGINE": "django.db.backends.oracle",
        "NAME": "host:port/servicename",
        "USER": "your_user",
        "PASSWORD": "your_password",
    },
}

DATABASE_ROUTERS = ["dynamic_db_router.router.DynamicDbRouter"]
