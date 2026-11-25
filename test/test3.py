# ======================== COT 引导与结构化约束 ========================
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

COT_INSTRUCTION = """
【思考步骤】
在生成 SQL 之前，请按以下步骤思考：
1. 确认金额口径（net_amount vs gross_amount）和成本口径
2. 确认是否需要过滤 order_status = 'completed'
3. 确认时间范围和汇率转换需求
4. 最后生成 SQL
"""

OUTPUT_CONSTRAINTS = """
【输出约束】
1. 只输出 SQL 语句，不需要解释
2. 使用标准 MySQL 语法
3. 确保字段名和表名与 Schema 一致
4. 如果涉及多表查询，使用 JOIN 连接
5. 收入口径统一使用 net_amount，成本口径使用 material_cost + labor_cost
6. 统计销售额时，需要按订单日期的汇率转换为人民币
7. 所有收入类统计必须包含 WHERE order_status = 'completed'
"""

FEW_SHOT_EXAMPLES = """
示例1：
问题：查询已完成订单的总数量
SQL: SELECT COUNT(*) FROM sales_orders WHERE order_status = 'completed';

示例2：
问题：按客户类型统计订单数量
SQL: SELECT c.customer_type, COUNT(*) AS order_count FROM sales_orders o JOIN dim_customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'completed' GROUP BY c.customer_type;

示例3：
问题：查询2026年第一季度的总费用
SQL: SELECT SUM(rd_expense + selling_expense + admin_expense + finance_expense) AS total_expense FROM finance_expenses WHERE expense_date >= '2026-01-01' AND expense_date < '2026-04-01';
"""

"""构造包含 COT 和结构化约束的 Prompt (ICIO 框架)"""
prompt = ChatPromptTemplate.from_messages([
    ("system","""你是一个专业的 SQL 生成助手，擅长根据业务问题生成标准 MySQL 查询语句。

【数据库 Schema】
{SCHEMA}

【示例】
{FEW_SHOT_EXAMPLES}

{COT_INSTRUCTION}

{OUTPUT_CONSTRAINTS}

【用户问题】
{user_question}

请直接输出 SQL:
""")
])

"""
Schema 自动生成工具

从 MySQL 数据库连接中读取表结构，按固定模板生成 Schema 字符串，
替代完全手写的方式。


"""

import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "chatbi_mvp"),
    "charset": "utf8mb4"
}


def get_tables(cursor) -> list[str]:
    """获取数据库中的所有表名"""
    cursor.execute("SHOW TABLES")
    return [row[0] for row in cursor.fetchall()]


def get_columns(cursor, table_name: str) -> list[dict]:
    """获取指定表的所有字段信息"""
    cursor.execute(f"SHOW FULL COLUMNS FROM `{table_name}`")
    columns = []
    for row in cursor.fetchall():
        columns.append({
            "name": row[0],
            "type": row[1],
            "comment": row[8] or ""
        })
    return columns


def get_foreign_keys(cursor, table_name: str) -> list[dict]:
    """获取指定表的外键信息"""
    cursor.execute(f"""
        SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = '{table_name}'
        AND REFERENCED_TABLE_NAME IS NOT NULL
    """)
    fks = []
    for row in cursor.fetchall():
        fks.append({
            "column": row[0],
            "ref_table": row[1],
            "ref_column": row[2]
        })
    return fks


def build_schema_string(cursor, table_name: str) -> str:
    """为单张表生成 Schema 描述字符串"""
    columns = get_columns(cursor, table_name)
    fks = get_foreign_keys(cursor, table_name)
    fk_map = {fk["column"]: fk for fk in fks}

    lines = [f"表: {table_name}"]
    for col in columns:
        name = col["name"]
        col_type = col["type"]
        comment = col["comment"]

        parts = [f"  {name} ({col_type})"]
        if name in fk_map:
            fk = fk_map[name]
            parts.append(f"外键 → {fk['ref_table']}.{fk['ref_column']}")
        elif comment:
            parts.append(comment)

        lines.append(" ".join(parts))

    return "\n".join(lines)


def generate_schema() -> str:
    """连接数据库，生成所有表的 Schema 描述"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            tables = get_tables(cursor)
            schemas = []
            for table in tables:
                schema_str = build_schema_string(cursor, table)
                schemas.append(schema_str)
            return "\n\n".join(schemas)
    finally:
        conn.close()

def generate_sql(user_question: str, ) -> str:
    """调用 LLM 生成 SQL"""
    client = ChatOpenAI(
        api_key=os.environ.get("API_KEY"),
        base_url=os.environ.get("BASE_URL"),
        model=os.environ.get("LLM_MODEL"),
    )
    schema = generate_schema()

    chain = prompt | client | StrOutputParser()

    result = chain.invoke(input={"SCHEMA": schema,
                                 "user_question": user_question,
                                 "FEW_SHOT_EXAMPLES": FEW_SHOT_EXAMPLES,
                                 "COT_INSTRUCTION": COT_INSTRUCTION,
                                 "OUTPUT_CONSTRAINTS": OUTPUT_CONSTRAINTS,})



    sql = re.sub(r"```sql\s*|\s*```", "", result.strip())
    return sql


def run(question: str) -> None:
    """运行并输出生成的 SQL"""
    print("=" * 60)
    print(f"问题: {question}")
    print("=" * 60)

    sql = generate_sql(question)
    print(f"生成 SQL: \n{sql}\n")
    print("可将上述 SQL 复制到 MySQL 客户端执行验证。\n")






if __name__ == "__main__":
    questions = "欧洲市场最近三个月的销售数量是多少",
    run(questions)
