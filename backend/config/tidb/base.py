"""MySQL backend tweaked for TiDB."""

from django.db.backends.mysql import base, schema


class DatabaseSchemaEditor(schema.DatabaseSchemaEditor):
    def skip_default(self, field):
        # TiDB rejects expression defaults like JSON DEFAULT ('{}'); Django backfills existing rows with an UPDATE instead.
        return self._is_limited_data_type(field) or super().skip_default(field)


class DatabaseWrapper(base.DatabaseWrapper):
    SchemaEditorClass = DatabaseSchemaEditor
