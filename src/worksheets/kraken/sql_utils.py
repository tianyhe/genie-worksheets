from typing import Dict

from suql import suql_execute


def execute_sql(
    sql: str,
    table_w_ids: Dict,
    database_name: str,
    suql_model_name="gpt-4-turbo",
    embedding_server_address: str = "http://127.0.0.1:8509",
    source_file_mapping: Dict = {},
    api_base=None,
    api_version=None,
    api_key=None,
    db_host=None,
    db_port=None,
    db_username=None,
    db_password=None,
):
    try:
        results, column_names, _ = suql_execute(
            sql,
            table_w_ids,
            database_name,
            embedding_server_address=embedding_server_address,
            source_file_mapping=source_file_mapping,
            llm_model_name=suql_model_name,
            disable_try_catch=True,
            disable_try_catch_all_sql=True,
            api_base=api_base,
            api_version=api_version,
            api_key=api_key,
            host=db_host,
            port=db_port,
            select_username=db_username,
            select_userpswd=db_password,
        )
        status = None
    except Exception as e:
        results = None
        column_names = None
        status = str(e)
        # print("Error in execute_sql: ", status)

    return results, column_names, status
