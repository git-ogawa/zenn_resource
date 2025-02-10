

## dify の `openAI` model provider に `opentelemetry-instrumentation-openai-v2` の計測を組み込む手順


デプロイ自体は [Deploy with Docker Compose](https://docs.dify.ai/getting-started/install-self-hosted/docker-compose) に従う。

## 手順

1. dify のリポジトリを clone

```
git clone https://github.com/langgenius/dify.git
```

2. `api/core/model_runtime/model_providers/openai/llm/llm.py` を編集して opentelemetry の計測コードを追加する。コード内の適当な場所に以下をまるごと追加すれば良い。

```python:llm.py
# NOTE: OpenTelemetry Python Logs and Events APIs are in beta
from opentelemetry import _events, _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider, view
from opentelemetry.sdk.metrics._internal.aggregation import (
    ExplicitBucketHistogramAggregation,
)
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# configure tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

# configure logging and events
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)
_events.set_event_logger_provider(EventLoggerProvider())

# configure metrics
views = [
    view.View(
        instrument_name="gen_ai.client.token.usage",
        aggregation=ExplicitBucketHistogramAggregation(
            [
                1,
                4,
                16,
                64,
                256,
                1024,
                4096,
                16384,
                65536,
                262144,
                1048576,
                4194304,
                16777216,
                67108864,
            ]
        ),
    ),
    view.View(
        instrument_name="gen_ai.client.operation.duration",
        aggregation=ExplicitBucketHistogramAggregation(
            [
                0.01,
                0.02,
                0.04,
                0.08,
                0.16,
                0.32,
                0.64,
                1.28,
                2.56,
                5.12,
                10.24,
                20.48,
                40.96,
                81.92,
            ]
        ),
    ),
]

metric_exporter = OTLPMetricExporter()
metric_reader = PeriodicExportingMetricReader(metric_exporter)
provider = MeterProvider(metric_readers=[metric_reader], views=views)
metrics.set_meter_provider(provider)

# instrument OpenAI
OpenAIInstrumentor().instrument()
```

3. `api/pyproject.toml` に opentelemetry 関連のパッケージを追加 [pyproject.toml](pyproject.toml)。既存のパッケージのバージョンと依存関係がいくつか競合するので適宜修正する。
4. `api` 内で `poetry lock` を実行して `poetry.lock` を更新。
5. `api/Dockerfile` に otel エンドポイントなどを追加する [Dockerfile](Dockerfile)。このあたりは `docker-compose.yml` で定義してもいいかも。

```
# Update this with your real OpenAI API key
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://xxxx:4317
ENV OTEL_EXPORTER_OTLP_PROTOCOL=grpc
ENV OTEL_SERVICE_NAME=[service_name]
ENV OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

6. トップディレクトリで `make build-api` を実行して api イメージをビルドする。api のソースコードみ変更を加えているためビルドするのは api イメージだけで良い。
7. ビルドしたイメージを使用するように `docker/docker-compose.yml` を修正。

```diff
services:
  # API service
  api:
-    image: langgenius/dify-api:0.15.3
+    image: langgenius/dify-api
    restart: always
```

8. `docker compose up -d` で各アプリを起動。
9. dify にログインして openAI モデルを登録する。
