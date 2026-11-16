# TiDB compatibility tweaks for Django
try:
    from django.db.backends.mysql.features import DatabaseFeatures
    from django.db.backends.mysql.schema import DatabaseSchemaEditor

    # 1. Relax version check: TiDB reports MySQL 8.0.11 compatibility.
    DatabaseFeatures.minimum_database_version = property(
        lambda self: (10, 11) if getattr(self.connection, "mysql_is_mariadb", False) else (8, 0)
    )

    # 2. TiDB does not support adding a column and foreign key constraint in the
    # same ALTER TABLE statement ("Key column '...' doesn't exist in table").
    # Setting this to None forces Django to create the column first, then add the constraint.
    DatabaseSchemaEditor.sql_create_column_inline_fk = None
except ImportError:
    pass
