"""Narrow analytical SQL grammar; still requires least-privilege DB access."""

from sqlglot import exp, parse
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.scope import traverse_scope

MAX_SQL_CHARS = 2000
TABLES = frozenset({"customers", "products", "orders"})
FUNCTIONS = frozenset(
    {
        "SUM",
        "COUNT",
        "AVG",
        "MIN",
        "MAX",
        "ROUND",
        "COALESCE",
        "NULLIF",
        "CAST",
        "EXTRACT",
        "DATE_TRUNC",
        "TIMESTAMP_TRUNC",
        "LOWER",
        "UPPER",
        "ABS",
        "CURRENT_DATE",
        "CURRENT_TIMESTAMP",
    }
)


def validate_sql(sql):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL_CHARS:
        raise ValueError("SQL must be nonempty and at most 2000 characters.")
    try:
        statements = [s for s in parse(sql, read="postgres") if s is not None]
    except ParseError:
        raise ValueError("SQL could not be parsed.") from None
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise ValueError("Only one analytical SELECT query is permitted.")
    tree = statements[0]
    for node in tree.walk():
        if isinstance(
            node,
            (
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Create,
                exp.Drop,
                exp.Command,
                exp.Into,
                exp.Lock,
                exp.TableSample,
                exp.DML,
                exp.DDL,
            ),
        ):
            raise ValueError("Writes and locking queries are not permitted.")
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise ValueError("Recursive queries are not permitted.")
        if isinstance(node, exp.Dot):
            raise ValueError("Qualified function/object expressions are not permitted.")
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
            if name not in FUNCTIONS:
                raise ValueError("Function is outside the analytical allowlist.")
        if isinstance(node, exp.DataType) and node.this == exp.DataType.Type.USERDEFINED:
            raise ValueError("User-defined casts are not permitted.")
    base_tables = 0
    try:
        for scope in traverse_scope(tree):
            for source in scope.sources.values():
                if isinstance(source, exp.Table):
                    if (
                        source.catalog
                        or source.db != "sales"
                        or source.name not in TABLES
                        or not isinstance(source.this, exp.Identifier)
                    ):
                        raise ValueError("Use only qualified sales.customers, sales.products or sales.orders.")
                    base_tables += 1
    except OptimizeError:
        raise ValueError("Ambiguous SQL table scope.") from None
    if not base_tables:
        raise ValueError("Business queries must read an approved sales relation.")
    return tree.sql(dialect="postgres")
