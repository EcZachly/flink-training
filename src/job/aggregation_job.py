from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table import EnvironmentSettings, DataTypes, TableEnvironment, StreamTableEnvironment
from pyflink.table.expressions import lit, col
from pyflink.table.window import Tumble


def create_events_aggregated_sink(t_env):
    table_name = 'processed_events_aggregated_source'
    sink_ddl = f"""
        CREATE TABLE {table_name} (
            event_hour TIMESTAMP(3),
            num_hits BIGINT
        ) WITH (
            'connector' = 'jdbc',
            'url' = 'jdbc:postgresql://postgres:5432/postgres',
            'table-name' = '{table_name}',
            'username' = 'postgres',
            'password' = 'postgres',
            'driver' = 'org.postgresql.Driver'
        );
        """
    t_env.execute_sql(sink_ddl)
    return table_name

def create_processed_events_source_kafka(t_env):
    table_name = "process_events_kafka"
    pattern = "yyyy-MM-dd HH:mm:ss"
    sink_ddl = f"""
        CREATE TABLE {table_name} (
            ip VARCHAR,
            event_timestamp VARCHAR,
            referrer VARCHAR,
            host VARCHAR,
            url VARCHAR,
            geodata VARCHAR,
            window_timestamp AS TO_TIMESTAMP(event_timestamp, '{pattern}'),
            WATERMARK FOR window_timestamp AS window_timestamp - INTERVAL '15' SECOND
        ) WITH (
            'connector' = 'kafka',
            'properties.bootstrap.servers' = 'redpanda-1:29092',
            'topic' = 'test-topic',
            'scan.startup.mode' = 'earliest-offset',
            'properties.auto.offset.reset' = 'earliest',
            'format' = 'json'
        );
        """
    t_env.execute_sql(sink_ddl)
    return table_name


def log_aggregation():
    # Set up the execution environment
    env = StreamExecutionEnvironment.get_execution_environment()
    env.enable_checkpointing(10)
    env.set_parallelism(3)

    # Set up the table environment
    settings = EnvironmentSettings.new_instance().in_streaming_mode().build()
    t_env = StreamTableEnvironment.create(env, environment_settings=settings)

    try:
        # Create Kafka table
        source_table = create_processed_events_source_kafka(t_env)
        aggregated_table = create_events_aggregated_sink(t_env)
        t_env.from_path(source_table)\
            .window(
            Tumble.over(lit(5).minutes).on(col("window_timestamp")).alias("w")
        ).group_by(
            col("w"),
            col("host")
        ) \
            .select(
                    col("w").start.alias("event_hour"),
                    col("host"),
                    col("host").count.alias("num_hits")
            ) \
            .execute_insert(aggregated_table).wait()

    except Exception as e:
        print("Writing records from Kafka to JDBC failed:", str(e))


if __name__ == '__main__':
    log_aggregation()
