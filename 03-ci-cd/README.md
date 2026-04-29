# 03 - CI/CD 로 자동화되는 CIFAR-10 파이프라인

이 챕터는 앞의 두 챕터에서 배운 컴포넌트 작성 방식과 데이터 공유 방식을 실제 "머신러닝 파이프라인답게" 조합해, **GitHub Actions 를 통해 자동으로 빌드되고 배포되는** 구조를 만드는 것이 목표입니다. 로컬에서 한 번 돌려보는 수준을 넘어, main 브랜치에 머지만 하면 이미지가 다시 빌드되고 최신 커밋 기준으로 파이프라인이 Vertex AI 에 제출되는 일련의 흐름을 경험해볼 수 있습니다.

## 전체 그림

파이프라인은 세 단계(컴포넌트)로 나뉘어 있습니다. **`data-preparation`** 은 `torchvision` 으로 CIFAR-10 을 내려받고, 학습용/검증용 이미지 텐서와 레이블 텐서를 `.pt` 파일 두 개로 저장합니다. **`train`** 은 그 학습용 텐서를 받아 간단한 CNN (두 개의 Conv + MaxPool 블록 + 두 개의 FC 층)을 지정된 epoch/batch/lr 로 학습시키고, 학습된 모델의 `state_dict` 를 저장합니다. **`evaluation`** 은 그 모델과 검증용 텐서를 받아 test accuracy 를 계산한 뒤 `{"accuracy": ..., "correct": ..., "total": ...}` 형태의 JSON 을 저장합니다. 세 단계가 모두 아티팩트 경로로 연결되어 있어서, 한 단계가 만든 결과물이 자연스럽게 다음 단계의 입력으로 전달됩니다.

세 컴포넌트는 모두 **독립된 Docker 이미지로 빌드** 됩니다. `03-ci-cd/data-preparation/`, `03-ci-cd/train/`, `03-ci-cd/evaluation/` 각 폴더에 `Dockerfile` 과 `main.py` 가 있고, GitHub Actions 워크플로우가 폴더별로 이미지를 빌드해 `gcr.io/<project>/<component-name>:<short-sha>` 태그로 GCR 에 푸시합니다. 이후 파이프라인 YAML 을 컴파일할 때 이 이미지 태그를 환경변수로 주입해서, 어떤 파이프라인 실행이 어떤 커밋의 이미지를 썼는지가 명확히 남도록 구성했습니다.

## 컴포넌트 간 데이터 공유 방식

이 챕터는 챕터 02 에서 배운 **KFP 아티팩트 방식** 을 사용합니다. 즉, 컴포넌트 시그니처에 `Output[Dataset]`, `Output[Model]`, `Input[Dataset]`, `Input[Model]`, `Output[Metrics]` 같은 타입을 선언하고, 실제로는 `.path` 속성에 들어 있는 경로(Vertex AI 가 자동 매핑하는 GCS 경로)를 컨테이너의 CLI 인자로 전달합니다. 그래서 컨테이너 안의 `main.py` 는 `--train-output /gcs/.../train.pt` 같은 인자를 받아 그 경로에 텐서를 저장하기만 하면 됩니다.

데이터 흐름은 다음과 같습니다. `data-preparation` 이 `train_dataset` 과 `test_dataset` 두 개의 Dataset 아티팩트를 만들고, `train` 은 그 중 `train_dataset` 을 입력으로 받아 `model` 이라는 Model 아티팩트를 출력합니다. 마지막으로 `evaluation` 은 `test_dataset` 과 `model` 을 함께 받아 `metrics` Metrics 아티팩트를 출력합니다. 이 연결 관계 덕분에 실행 순서도 자동으로 `data-preparation → train → evaluation` 으로 결정됩니다(챕터 01 에서 배운 자동 선후관계).

## 컴퓨팅 스펙을 바꿀 수 있게 만든 방법

세 컴포넌트 각각에 대해 CPU 코어 수와 메모리를 **파이프라인 파라미터** 로 노출했습니다. 예를 들어 `cpu_train`, `memory_train` 을 바꾸면 train 컴포넌트의 리소스만 따로 조정됩니다. 파이프라인 코드에서는 `train_task.set_cpu_limit(cpu_train).set_memory_limit(memory_train)` 처럼 파라미터를 그대로 setter 에 넘기고, 제출 시점에 `--param cpu_train=8 --param memory_train=32G` 같은 형태로 오버라이드할 수 있습니다. 기본값은 일반적인 CPU 학습에 무난한 선에서 `2/8G`(data-preparation, evaluation), `4/16G`(train) 로 잡아두었습니다.

GPU 는 기본적으로 비활성 상태입니다. GPU 학습이 필요하면 두 가지를 바꿔야 합니다. 첫째, `03-ci-cd/pipeline.py` 에 주석으로 처리되어 있는 `train_task.set_accelerator_type("NVIDIA_TESLA_T4")` 와 `train_task.set_accelerator_limit(1)` 두 줄의 주석을 풀어 줍니다. 둘째, `03-ci-cd/train/Dockerfile` 의 base 이미지를 `python:3.12-slim` 대신 `pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime` 같은 CUDA 런타임 이미지로 교체하고, 해당 이미지가 이미 PyTorch 를 포함하므로 pip install 라인도 제거합니다. 이 두 변경은 CI 가 자동으로 해주지 않기 때문에 사람이 코드에 반영하고 커밋해야 합니다.

## 폴더 구조

```
03-ci-cd/
├── pipeline.py                  # 세 컨테이너 컴포넌트 + 파이프라인 정의 + 컴파일
├── ci-cd-pipeline.yaml          # 컴파일 결과 (CI 에서 자동 생성)
├── data-preparation/
│   ├── Dockerfile               # python:3.12-slim + torch(cpu) + torchvision
│   └── main.py                  # --train-output / --test-output
├── train/
│   ├── Dockerfile               # python:3.12-slim + torch(cpu)
│   └── main.py                  # --train-input / --model-output + epochs/batch/lr
└── evaluation/
    ├── Dockerfile               # python:3.12-slim + torch(cpu)
    └── main.py                  # --test-input / --model-input / --metrics-output
```

## 로컬에서 한 사이클 돌려보기 (CI 없이 검증)

CI 가 하는 일을 로컬에서 흉내 내보면, 각 단계가 실제로 무엇을 하는지 감이 잡힙니다. 먼저 Docker 가 GCR 로 push 할 수 있게 인증합니다.

```bash
gcloud auth configure-docker gcr.io
```

그 다음 세 컴포넌트 이미지를 차례로 빌드해서 푸시합니다. 태그는 CI 가 쓰는 `git rev-parse --short HEAD` 와 같은 짧은 SHA 로 잡는 것이 재현하기 좋습니다.

```bash
REGISTRY=gcr.io/my-gcp-project
TAG=$(git rev-parse --short HEAD)

for dir in 03-ci-cd/data-preparation 03-ci-cd/train 03-ci-cd/evaluation; do
  name=$(basename "$dir")
  docker build -t $REGISTRY/$name:$TAG "$dir"
  docker push $REGISTRY/$name:$TAG
done
```

이제 그 태그로 파이프라인을 컴파일합니다. 환경변수 두 개를 주입하면 `pipeline.py` 가 이 값들을 `dsl.ContainerSpec(image=...)` 에 그대로 박아 넣습니다.

```bash
IMAGE_REGISTRY=$REGISTRY IMAGE_TAG=$TAG \
    uv run python 03-ci-cd/pipeline.py
```

그러면 `03-ci-cd/ci-cd-pipeline.yaml` 이 해당 커밋/태그를 참조하는 형태로 만들어집니다. 마지막으로 루트의 `submit.py` 로 제출합니다.

```bash
uv run python submit.py \
    --project my-gcp-project \
    --region us-central1 \
    --pipeline-root gs://my-bucket/pipeline-root \
    --template 03-ci-cd/ci-cd-pipeline.yaml \
    --param epochs=3 --param batch_size=128 --param lr=0.001
```

이 과정이 잘 되면 CI 가 돌았을 때도 동일하게 동작한다고 기대할 수 있습니다.

## GitHub Actions 워크플로우의 동작

워크플로우 파일은 `.github/workflows/03-ci-cd.yml` 에 있습니다. `main` 브랜치에 푸시가 발생하고, 그 커밋이 `03-ci-cd/**`, `submit.py`, `pyproject.toml`, `uv.lock`, 또는 워크플로우 파일 자체를 건드린 경우에만 실행됩니다(경로 필터). Actions 탭에서 `workflow_dispatch` 로 수동 실행도 가능합니다.

실행되면 먼저 `actions/checkout@v4` 로 repository 를 받아온 뒤, `${GITHUB_SHA::7}` 을 `IMAGE_TAG` 로 잡아 둡니다. 그 다음 `google-github-actions/auth@v2` 가 Workload Identity Federation 을 통해 단기 토큰을 발급받고, `setup-gcloud@v2` 로 gcloud CLI 를 준비합니다. `gcloud auth configure-docker gcr.io` 로 Docker 가 GCR 로 푸시할 수 있게 하고, `docker buildx` 로 `03-ci-cd/*/Dockerfile` 을 glob 해서 각 폴더를 **짧은 SHA 태그 + `latest` 태그** 로 동시에 빌드/푸시합니다.

이미지 푸시가 끝나면 `astral-sh/setup-uv@v4` 로 uv 를 설치하고 `uv sync --frozen` 으로 의존성을 락 기준으로 설치합니다. 이어서 `IMAGE_TAG` 환경변수를 같은 값으로 지정한 상태에서 `python 03-ci-cd/pipeline.py` 를 돌려 YAML 을 컴파일하고, 마지막으로 루트 `submit.py` 에 저장소 Variables 로 설정된 GCP 프로젝트/리전/pipeline root/서비스 계정/WIF provider 값을 넘겨 파이프라인을 제출합니다. 캐싱을 활성화해 두었기 때문에, 동일한 입력에 대한 재실행이 있으면 변경되지 않은 컴포넌트는 자동으로 건너뜁니다.

## GCP 쪽 사전 설정

이 워크플로우를 실제로 돌리려면 GCP 쪽에 몇 가지 준비가 필요합니다. 각 단계가 왜 필요한지 간단히 설명합니다.

**API 활성화.** `Vertex AI API` 와 `Container Registry API` 를 해당 프로젝트에서 활성화해야 합니다. 신규 프로젝트라면 콘솔에서 한 번 클릭하면 됩니다.

**서비스 계정 준비.** 예컨대 `vertex-ci@<project>.iam.gserviceaccount.com` 같은 계정을 만들고 아래 역할을 부여합니다. `roles/aiplatform.user` 는 파이프라인을 제출할 수 있게 해주고, `roles/storage.admin` 은 pipeline root 용 GCS 버킷 쓰기와 GCR(이미지 저장소도 내부적으로 GCS) 에 대한 권한을 동시에 커버합니다. 파이프라인 내부에서 별도 서비스 계정을 지정하지 않는다면, 이 계정이 파이프라인 실행 SA 로도 사용됩니다. `roles/iam.serviceAccountUser` 는 WIF 로 이 계정을 assume 할 때 필요합니다.

**Workload Identity Federation 설정.** 이 부분이 가장 번거롭지만 가장 중요합니다. GitHub Actions 에 긴 수명의 SA 키 JSON 을 올리는 대신, GitHub 가 발급하는 OIDC 토큰으로 GCP 에 인증하는 방식입니다. Workload Identity Pool 을 하나 만들고, 그 안에 GitHub 용 Provider 를 추가한 뒤, 위에서 만든 서비스 계정에 "이 GitHub repo 가 impersonate 할 수 있다" 는 IAM 바인딩 (`roles/iam.workloadIdentityUser`) 을 걸어 주면 됩니다. 설정이 끝나면 Provider 의 리소스 이름을 repo Variables 에 넣습니다.

**pipeline root 버킷 생성.** `gs://<bucket>/pipeline-root` 처럼 쓸 GCS 버킷을 미리 만들어 두어야 합니다. 위 서비스 계정이 이 버킷에 쓰기 권한을 가지고 있어야 합니다.

## GitHub repository Variables 에 넣어야 하는 값

Settings → Secrets and variables → Actions → **Variables** 탭에서 아래 다섯 개를 추가합니다. Secrets 가 아니라 **Variables** 입니다(민감 정보가 아니므로).

`GCP_PROJECT` 에는 프로젝트 ID 를, `GCP_REGION` 에는 예를 들어 `us-central1` 을, `PIPELINE_ROOT` 에는 `gs://<bucket>/pipeline-root` 를 넣습니다. `WIF_PROVIDER` 는 `projects/<project-number>/locations/global/workloadIdentityPools/<pool>/providers/<provider>` 형태의 전체 리소스 경로이고, `WIF_SERVICE_ACCOUNT` 는 위에서 만든 서비스 계정 이메일(`vertex-ci@<project>.iam.gserviceaccount.com`) 입니다.

## GCR 이 deprecated 이라면 (Artifact Registry 로 이전)

신규 프로젝트에서는 GCR 이 이미 deprecated 이고 Artifact Registry 사용이 권장됩니다. 이전은 생각보다 간단합니다. `IMAGE_REGISTRY` 의 값을 `us-central1-docker.pkg.dev/<project>/<repo>` 형태로 바꾸고(미리 `gcloud artifacts repositories create` 로 저장소를 만들어 두어야 함), 워크플로우의 `gcloud auth configure-docker gcr.io` 를 해당 지역 도메인(`us-central1-docker.pkg.dev`) 으로 바꾸고, 서비스 계정에 `roles/artifactregistry.writer` 를 추가하면 됩니다. 파이프라인 코드는 손댈 필요가 없습니다 — 환경변수만 바뀌면 이미지 URL 이 자동으로 새 저장소를 가리키게 됩니다.
