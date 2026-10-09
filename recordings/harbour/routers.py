"""The router of chapter 11's recording: the office's logbooks are kept in the database "archive"."""

LOGBOOKS = {"logbook", "logentry"}


class LogbookRouter:
    def db_for_read(self, model, **hints):
        if model._meta.model_name in LOGBOOKS:
            return "archive"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.model_name in LOGBOOKS:
            return "archive"
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name in LOGBOOKS:
            return db == "archive"
        return None
