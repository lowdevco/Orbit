# TiDB reports its version as MySQL 8.0.11. Django 6.1 bumped the minimum required
# MySQL version check to 8.4 (due to upstream Oracle EOL).
# We relax the check to (8, 0) so TiDB connects cleanly.
try:
    from django.db.backends.mysql.features import DatabaseFeatures

    DatabaseFeatures.minimum_database_version = property(
        lambda self: (10, 11) if getattr(self.connection, "mysql_is_mariadb", False) else (8, 0)
    )
except ImportError:
    pass
