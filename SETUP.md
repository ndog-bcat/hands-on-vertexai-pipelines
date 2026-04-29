# 초기 셋업 — GCP 프로젝트와 파이프라인 실행 환경 준비

이 문서는 이 리포의 어떤 챕터든 돌리기 전에 딱 한 번 해두어야 하는 GCP/로컬 준비 과정을 정리한 것입니다. gcloud CLI 설치, 로그인, 프로젝트 지정, API 활성화, 그리고 **pipeline root 로 쓸 GCS 버킷 생성** 까지를 다룹니다.

## 0. gcloud CLI 설치

로컬에 `gcloud` 가 없다면 먼저 설치합니다. macOS 에서는 Homebrew 가 가장 편합니다.

```bash
brew install --cask google-cloud-sdk
source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
gcloud --version
```

brew 를 쓰지 않는다면 공식 스크립트로도 설치할 수 있습니다.

```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud --version
```

## 1. 로그인 — 두 종류를 모두 해야 합니다

gcloud 인증은 서로 다른 경로 두 가지로 나뉘어 있어서, 이 리포를 돌리려면 **둘 다** 해야 합니다.

첫 번째는 **gcloud CLI 본인이 쓰는 인증**입니다. `gcloud projects list` 같은 커맨드를 실행할 때 이 인증이 사용됩니다.

```bash
gcloud auth login
```

두 번째는 **Application Default Credentials(ADC)** 입니다. Python 의 `google-cloud-aiplatform` SDK 를 포함해 대부분의 Google Cloud 클라이언트 라이브러리가 이 credential 을 읽어서 인증합니다. 파이프라인을 제출하는 스크립트(`submit.py`, `01-direct-run.py`) 는 이 경로를 사용하므로 반드시 해야 합니다.

```bash
gcloud auth application-default login
```

두 번째 명령을 실행하면 ADC 가 `~/.config/gcloud/application_default_credentials.json` 에 저장됩니다. 이 파일은 별도로 신경 쓸 필요 없이, 라이브러리가 알아서 읽어갑니다.

## 2. 프로젝트와 quota project 지정

로그인 직후에는 "어느 프로젝트를 쓸지" 가 아직 정해지지 않은 상태입니다. 본인이 사용할 프로젝트 ID 를 확인하고 기본값으로 설정합니다.

```bash
gcloud projects list
gcloud config set project <PROJECT_ID>
```

여기에 더해 **ADC 의 quota project** 도 같이 지정하는 것이 좋습니다. 이게 빠져 있으면 Python SDK 가 호출할 때 "쿼터 프로젝트가 없다" 는 경고가 반복해서 뜨고, 어떤 API 는 정상 동작하지 않을 수 있습니다.

```bash
gcloud auth application-default set-quota-project <PROJECT_ID>
```

## 3. 필요한 API 활성화

이 리포에서 사용하는 API 세 가지를 한 번에 켭니다. 신규 프로젝트가 아니라면 이미 켜져 있는 경우가 많고, 이미 켜져 있는 API 에 다시 enable 을 호출해도 문제 없습니다.

```bash
gcloud services enable \
    aiplatform.googleapis.com \
    compute.googleapis.com \
    storage.googleapis.com \
    --project <PROJECT_ID>
```

## 4. Pipeline root 로 쓸 GCS 버킷 생성

Vertex AI Pipelines 는 모든 파이프라인 실행의 산출물(아티팩트, 로그 위치 메타데이터 등)을 GCS 위에 올립니다. 그 최상단 경로를 **pipeline root** 라고 부르고, 파이프라인을 제출할 때 항상 이 경로를 지정해야 합니다. 그래서 전용으로 쓸 버킷을 하나 미리 만들어 둡니다.

### 버킷 이름 정하기

GCS 버킷 이름은 **전역(전체 GCP 사용자 공통)으로 유일** 해야 합니다. 충돌을 피하기 위해 보통 프로젝트 ID 를 접두어로 넣습니다. 이 리포에서는 아래 규칙을 따르기를 권장합니다.

```
gs://<PROJECT_ID>-vertex-pipelines
```

예: 프로젝트 ID 가 `test-gcp-490616` 이라면 버킷은 `gs://test-gcp-490616-vertex-pipelines` 가 됩니다.

### 리전 선택

파이프라인이 실행되는 리전(`GCP_REGION`) 과 **같은 리전** 에 버킷을 만드는 것이 성능과 비용 면에서 유리합니다. 리전이 다르면 파이프라인 워커가 버킷에서 데이터를 읽을 때마다 리전 간 전송 요금이 붙고 레이턴시도 커집니다. 이 리포의 기본 리전은 `us-central1` 이므로 버킷도 거기에 만듭니다.

### 생성 명령

```bash
gcloud storage buckets create gs://<PROJECT_ID>-vertex-pipelines \
    --location=us-central1 \
    --project <PROJECT_ID>
```

이미 만들어져 있는지 확인하려면:

```bash
gcloud storage buckets list --project <PROJECT_ID>
```

### 버킷 안의 경로 규칙

리포의 스크립트들은 `PIPELINE_ROOT` 환경변수에 `gs://<bucket>/pipeline-root` 처럼 **버킷 하위의 특정 경로** 를 지정해서 사용합니다. 이렇게 해두면 나중에 같은 버킷을 여러 용도로 나눠 쓰기 편합니다. 예를 들면:

```
gs://test-gcp-490616-vertex-pipelines/
├── pipeline-root/        ← PIPELINE_ROOT 으로 쓸 경로 (Vertex AI 가 자동 생성)
├── 02-data-sharing/      ← 챕터 02 의 gcs-string / gcs-fuse 파이프라인이 만들 산출물
└── ...
```

pipeline-root 하위 경로는 파이프라인을 처음 제출하는 순간 Vertex AI 가 자동으로 만듭니다. 버킷만 있으면 됩니다.

## 5. 파이프라인 실행 서비스 계정에 버킷 권한 부여 (중요)

여기서 한 번은 걸려본다고 생각하면 되는 함정입니다. 콘솔이나 로컬에서 파이프라인을 제출하려고 하면 다음과 같은 에러가 나옵니다.

```
이 파이프라인을 실행하려면 서비스 계정
("49784850238-compute@developer.gserviceaccount.com")에 다음 역할이나 권한이 필요합니다.
  storage.objects.get
  storage.objects.create
```

이게 왜 나오는지를 이해하면 해결도 명확해집니다. Vertex AI Pipelines 는 **파이프라인을 제출하는 사람의 권한** 이 아니라, "파이프라인 실행에 쓰이는 별도의 서비스 계정" 으로 파이프라인 워커를 띄우고 GCS 에 접근합니다. 제출할 때 이 **실행 서비스 계정** 을 지정하지 않으면 프로젝트의 **기본 Compute Engine 서비스 계정**(`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`) 이 자동 선택됩니다. 이 SA 가 pipeline root 버킷에 대해 객체 읽기/쓰기 권한을 가지고 있지 않으면 위 에러가 뜹니다.

로그인한 내 사용자 계정이 Owner 라도 소용 없습니다. 실제 러너는 내 계정이 아니라 저 SA 이기 때문입니다.

### 해결 — 기본 Compute Engine SA 에 버킷 권한 부여

가장 권장되는 방법은 "pipeline root 로 쓸 버킷에만" 권한을 주는 것입니다. 프로젝트 전체 GCS 권한을 주지 않기 때문에 가장 안전합니다.

```bash
# 먼저 프로젝트 번호를 확인 (기본 compute SA 이메일에 들어감)
PROJECT_NUMBER=$(gcloud projects describe <PROJECT_ID> --format='value(projectNumber)')

gcloud storage buckets add-iam-policy-binding gs://<PROJECT_ID>-vertex-pipelines \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/storage.objectAdmin" \
    --project <PROJECT_ID>
```

부여가 적용되는 데 수 초 정도 걸릴 수 있습니다. 에러가 바로 같은 메시지로 재발하면 30 초 정도 기다렸다가 다시 제출하세요.

### 고민거리 — 전용 실행 SA 를 쓸지, 기본 SA 에 권한을 얹을지

데모/학습 목적이라면 위처럼 기본 Compute SA 에 해당 버킷 권한만 얹어서 진행해도 괜찮습니다. 실제 운영에 가까운 환경에서는 파이프라인 전용 서비스 계정을 따로 만들고, 제출 시 `--service-account <email>` (루트 `submit.py` 지원) 로 지정하는 방식이 더 안전합니다. 이 패턴은 챕터 03 의 CI/CD 예제가 사용합니다.

### 내 사용자 계정이 가지고 있어야 하는 권한

제출 단계에서 **내가 직접 가지고 있어야 하는** 권한은 별개입니다. 본인 계정이 프로젝트 Owner 나 Editor 라면 추가 설정이 필요 없습니다. 더 세밀한 권한으로 운영하려면 아래 두 가지가 최소한 필요합니다.

- `roles/aiplatform.user` — 파이프라인 제출 및 조회
- `roles/storage.objectAdmin` — pipeline root 버킷에 읽기/쓰기 (내가 로컬에서 사전 업로드 등을 할 때)

또 파이프라인 실행 SA 를 명시적으로 지정해서 제출하려면, 내 계정이 그 SA 를 impersonate 할 수 있어야 합니다. 그 SA 에 대해 `roles/iam.serviceAccountUser` 가 내 계정에 부여되어 있어야 합니다.

CI (챕터 03 의 GitHub Actions) 에서는 사람 계정 대신 **Workload Identity Federation 으로 연결된 서비스 계정** 을 쓰게 되는데, 그 내용은 `03-ci-cd/README.md` 를 참고하세요.

## 6. (선택) GPU quota 확인

GPU 로 학습을 돌릴 계획이라면 현재 프로젝트의 GPU 쿼터를 미리 확인해두는 것이 좋습니다. 신규 프로젝트는 대부분의 GPU 에 대해 1개 까지만 허용되고, A100 같은 상위 GPU 는 0개 (즉, 쿼터 증가 요청 필요) 인 경우가 많습니다.

### 헷갈리지 말 것 — GPU 쿼터는 세 종류로 분리되어 있음

| 쿼터 메트릭 | 어디에 쓰이나 | 신규 프로젝트 디폴트 (T4) |
|---|---|---|
| `compute.googleapis.com/NVIDIA_T4_GPUS` | GCE 일반 VM (직접 띄우는 VM) | 1 |
| `aiplatform.googleapis.com/custom_model_training_nvidia_t4_gpus` | **Vertex AI 학습 잡** | **0** |
| `aiplatform.googleapis.com/custom_model_serving_nvidia_t4_gpus` | Vertex AI 모델 서빙(엔드포인트) | 1 |

세 가지가 **서로 별개로 운영** 됩니다. GCE 쪽 T4 가 1 이라도 Vertex AI 학습용 T4 는 0 인 경우가 흔합니다. 챕터 03 의 train 컴포넌트가 GPU 로 돌려면 두 번째 쿼터가 1 이상 있어야 합니다.

### Compute Engine 쪽 쿼터 (GCE VM 용)

```bash
gcloud compute regions describe us-central1 --project <PROJECT_ID> \
    --format="value(quotas)" | tr ',' '\n' | grep -iE 'gpu|nvidia'
```

### Vertex AI 학습 쿼터 (실제 학습 잡이 보는 쿼터)

콘솔 화면에서 가장 빨리 확인됩니다 (CLI 출력은 가공이 필요해서):

```
https://console.cloud.google.com/iam-admin/quotas?project=<PROJECT_ID>
```

상단 Filter 에 `Custom model training Nvidia T4` 를 입력하면 리전별 한도가 한 번에 보입니다.

### 쿼터 증가 신청

쿼터가 부족하면 위 콘솔 화면에서 해당 메트릭의 본인 리전 행을 체크 → **Edit Quotas** → 새 한도 값과 사유 입력 → 제출. 신규 계정은 보통 1–24 시간 안에 승인되지만 보장은 안 됩니다. GPU 학습을 계획한다면 미리 신청해 두는 것이 좋습니다.

## 7. 환경변수 export

여기까지 끝나면 이제 각 챕터의 스크립트가 읽을 환경변수 세 개를 셸에 export 해두면 됩니다. 매번 타이핑하기 귀찮으면 `~/.zshrc` 같은 곳에 박아 두어도 됩니다.

```bash
export GCP_PROJECT=<PROJECT_ID>
export GCP_REGION=us-central1
export PIPELINE_ROOT=gs://<PROJECT_ID>-vertex-pipelines/pipeline-root
```

이 상태가 되면 `01-direct-run.py` 같은 "한 번에 컴파일 + 제출" 스크립트도, 루트의 범용 `submit.py` 도 바로 돌아갑니다.

## 체크리스트

모든 단계를 끝내고 나서 아래 다섯 줄이 모두 통과하면 준비가 끝난 것입니다.

```bash
gcloud config get-value project             # → 설정한 PROJECT_ID 가 나와야 함
gcloud auth list --filter=status:ACTIVE     # → 로그인한 계정이 나와야 함
gcloud storage buckets list | grep vertex   # → 생성한 pipeline root 버킷이 보여야 함
gcloud services list --enabled \
    --filter="config.name:aiplatform.googleapis.com"   # → 한 줄이 나와야 함
gcloud storage buckets get-iam-policy \
    gs://<PROJECT_ID>-vertex-pipelines \
    --flatten="bindings[].members" \
    --filter="bindings.members:*-compute@developer.gserviceaccount.com" \
    --format="value(bindings.role)"                    # → roles/storage.objectAdmin 이 나와야 함
```
