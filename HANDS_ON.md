# 핸즈온 참가자 가이드 — Fork 해서 따라 하기

이 리포를 fork 한 뒤 본인의 GCP 프로젝트로 챕터 01–03 을 직접 실행해보고 싶을 때 보는 문서입니다. 핵심 원칙은 **"GCP 리소스(서비스 계정, 버킷, WIF 풀)는 각자 본인 프로젝트에 만들고, 본인이 fork 한 repo 에 연결한다"** 는 것입니다.

원본 작성자의 프로젝트(`test-gcp-490616` 등) 와는 무관하게 동작하도록 모든 리소스를 본인 명의로 새로 만든다고 생각하시면 됩니다.

## 사전 준비물 (한 번만)

핸즈온 시작 전에 갖춰져 있어야 하는 것들:

- 본인 명의의 **GCP 프로젝트** (결제 계정 연결됨, 무료 크레딧으로도 충분)
- **GitHub 계정**
- 로컬에 **gcloud CLI**, **git**, **Python 3.12+**, **uv** 설치
- (챕터 03 까지 진행할 거면) 로컬에 **Docker** 가 깔려 있으면 사전 검증이 편함 (필수는 아님)

gcloud CLI 가 없으면:

```bash
brew install --cask google-cloud-sdk
source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
gcloud --version
```

uv 가 없으면 [astral.sh/uv](https://docs.astral.sh/uv/) 에서 설치.

## 1단계 — Fork 와 로컬 클론

GitHub 의 원본 repo 페이지에서 **Fork** 버튼을 눌러 본인 계정으로 복제하시고, 로컬로 가져옵니다.

```bash
git clone git@github.com:<YOUR_USERNAME>/<FORK_NAME>.git
cd <FORK_NAME>
uv sync
```

`uv sync` 가 `pyproject.toml` / `uv.lock` 기준으로 가상환경을 만들고 의존성을 설치합니다.

## 2단계 — GCP 프로젝트 기초 설정

이 부분은 모두에게 공통입니다. 본인 프로젝트 ID 를 변수로 한 번 잡아두면 이후 명령이 깔끔합니다.

```bash
export PROJECT_ID=<your-gcp-project-id>
export REGION=us-central1
export BUCKET=${PROJECT_ID}-vertex-pipelines
```

### 2-1. 로그인 두 종류 + 프로젝트 / 쿼터 프로젝트 지정

gcloud CLI 와 Python SDK 가 쓰는 인증 경로가 달라서 둘 다 필요합니다.

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project $PROJECT_ID
gcloud auth application-default set-quota-project $PROJECT_ID
```

### 2-2. 필요한 API 한 번에 활성화

Vertex AI, Storage, IAM, Artifact Registry, Compute 까지.

```bash
gcloud services enable \
    aiplatform.googleapis.com \
    storage.googleapis.com \
    compute.googleapis.com \
    iamcredentials.googleapis.com \
    iam.googleapis.com \
    artifactregistry.googleapis.com \
    --project $PROJECT_ID
```

### 2-3. Pipeline root 버킷 생성

```bash
gcloud storage buckets create gs://$BUCKET --location=$REGION --project $PROJECT_ID
```

### 2-4. 기본 Compute Engine SA 에 버킷 권한 부여 (이거 안 하면 첫 실행에서 무조건 막힘)

Vertex AI Pipelines 는 파이프라인을 제출하는 사용자 권한이 아니라, **별도의 실행 SA** 로 GCS 에 접근합니다. 별도 지정 안 하면 기본 Compute Engine SA(`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`) 가 자동 선택됩니다. 이 SA 가 버킷 권한을 갖고 있어야 합니다.

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/storage.objectAdmin" \
    --project $PROJECT_ID
```

자세한 배경은 `SETUP.md` 를 참고하세요.

## 3단계 — 환경변수 export

각 챕터 스크립트가 읽는 세 개를 셸에 잡아둡니다. `~/.zshrc` 에 박아둬도 됩니다.

```bash
export GCP_PROJECT=$PROJECT_ID
export GCP_REGION=$REGION
export PIPELINE_ROOT=gs://$BUCKET/pipeline-root
```

## 4단계 — 챕터 01 실행

가장 빠른 검증은 한 방에 컴파일 + 제출되는 direct-run 입니다.

```bash
uv run python 01-first-pipeline/01-direct-run.py
```

성공하면 콘솔 URL 이 출력됩니다. 그 URL 로 들어가서 **`generate-data → process-data → notify`** 가 차례로 도는 것을 확인합니다 (총 5–7 분 정도).

컴파일과 제출을 분리해서 보고 싶으면:

```bash
uv run python 01-first-pipeline/01-first-pipeline.py
uv run python submit.py \
    --project $GCP_PROJECT --region $GCP_REGION \
    --pipeline-root $PIPELINE_ROOT \
    --template 01-first-pipeline/first-pipeline.yaml
```

자세한 챕터별 설명은 `01-first-pipeline/README.md` 참고.

## 5단계 — 챕터 02 실행

세 가지 데이터 공유 방식을 각각 컴파일하고 제출합니다.

```bash
# 컴파일
uv run python 02-data-sharing/02-gcs-string.py
uv run python 02-data-sharing/02-artifact-io.py
uv run python 02-data-sharing/02-gcs-fuse.py

# 제출 (gcs-string / gcs-fuse 는 bucket 파라미터 필요)
uv run python submit.py --project $GCP_PROJECT --region $GCP_REGION \
    --pipeline-root $PIPELINE_ROOT \
    --template 02-data-sharing/gcs-string.yaml \
    --param bucket=$BUCKET

uv run python submit.py --project $GCP_PROJECT --region $GCP_REGION \
    --pipeline-root $PIPELINE_ROOT \
    --template 02-data-sharing/artifact-io.yaml

uv run python submit.py --project $GCP_PROJECT --region $GCP_REGION \
    --pipeline-root $PIPELINE_ROOT \
    --template 02-data-sharing/gcs-fuse.yaml \
    --param bucket=$BUCKET
```

각 파이프라인이 콘솔에서 어떻게 다르게 보이는지 비교합니다. 특히 `artifact-io` 의 Artifacts 탭에 metadata 가 노출되는 것과, `gcs-string` / `gcs-fuse` 는 그 탭이 비어 있고 Parameters 탭에 경로만 있는 것을 직접 확인하세요. 자세한 비교는 `02-data-sharing/README.md`.

## 6단계 — 챕터 03 (CI/CD) 셋업

여기가 본격적입니다. 본인 fork 의 워크플로우가 본인 GCP 프로젝트로 이미지를 빌드/푸시하고 **파이프라인 템플릿을 등록** 하도록 연결해야 합니다. 워크플로우는 직접 실행을 트리거하지 않고, 콘솔의 "파이프라인 → 템플릿" 에 새 버전을 올려두기만 합니다. 실행은 본인이 콘솔에서 원하는 시점에 파라미터/컴퓨팅 스펙을 골라 trigger 합니다.

또한 monorepo CI 패턴을 적용해서 — 변경된 컴포넌트 폴더(`data-preparation/`, `train/`, `evaluation/`) 만 새 이미지로 빌드되고, 변경되지 않은 컴포넌트는 이전 이미지를 그대로 재사용합니다. 각 이미지의 태그는 그 폴더를 마지막으로 건드린 커밋의 short SHA 로 결정됩니다.

모든 명령은 위에서 잡은 `$PROJECT_ID`, `$REGION`, `$BUCKET`, `$PROJECT_NUMBER` 변수를 그대로 씁니다. 추가로 본인의 fork 정보를 변수로 잡으세요.

```bash
export GH_OWNER=<your-github-username>
export GH_REPO=<your-fork-name>
```

### 6-1. CI 전용 서비스 계정 생성

```bash
gcloud iam service-accounts create vertex-ci \
    --display-name "Vertex AI CI runner" \
    --project $PROJECT_ID

export CI_SA=vertex-ci@$PROJECT_ID.iam.gserviceaccount.com
```

### 6-2. SA 에 필요한 역할 부여

```bash
for role in \
    roles/aiplatform.user \
    roles/artifactregistry.writer \
    roles/storage.admin \
    roles/iam.serviceAccountUser
do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:$CI_SA" --role="$role"
done

# Pipeline root 버킷에서도 객체 R/W 권한을 명시적으로 부여
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
    --member="serviceAccount:$CI_SA" \
    --role="roles/storage.objectAdmin" \
    --project $PROJECT_ID
```

### 6-3. Docker 이미지용 Artifact Registry 저장소 생성

세 컴포넌트의 컨테이너 이미지가 들어갈 곳입니다. 신규 프로젝트는 GCR 가 비활성이라 **Artifact Registry 만 사용** 합니다 (워크플로우는 이미 AR 에 푸시하도록 구성되어 있음).

```bash
gcloud artifacts repositories create vertex-ci-images \
    --repository-format=docker \
    --location=$REGION \
    --description="CI/CD images for Vertex AI pipelines" \
    --project $PROJECT_ID
```

### 6-4. KFP 템플릿용 Artifact Registry 저장소 생성

컴파일된 파이프라인 YAML 을 등록할 KFP-format 저장소입니다. 콘솔의 "파이프라인 → 템플릿" 화면이 바로 이 저장소를 읽어 보여줍니다.

```bash
gcloud artifacts repositories create kfp-templates \
    --repository-format=kfp \
    --location=us \
    --description="KFP pipeline templates for Vertex AI" \
    --project $PROJECT_ID
```

> **위치(location) 가 `us` 멀티 리전인 점에 주의.** Vertex AI 콘솔의 템플릿 화면은 멀티 리전 KFP repo 를 잘 인식합니다. 단일 리전 (`us-central1`) 에 만들 수도 있지만 콘솔 표시 동작은 변동이 있을 수 있어 `us` 를 권장합니다.

생성 후 host URL 은 `https://us-kfp.pkg.dev/<PROJECT>/kfp-templates` 형태가 됩니다. 이 값은 7단계의 `KFP_HOST` Variable 로 들어갑니다.

### 6-5. Workload Identity Federation — 풀과 GitHub Provider 생성

서비스 계정 키 JSON 을 GitHub 시크릿에 올리지 않고, GitHub 가 발급하는 OIDC 토큰으로 GCP 인증하는 방식입니다.

```bash
# 1) Pool 생성
gcloud iam workload-identity-pools create github \
    --location=global \
    --display-name="GitHub Actions" \
    --project $PROJECT_ID

# 2) GitHub OIDC Provider 등록
gcloud iam workload-identity-pools providers create-oidc github-provider \
    --location=global \
    --workload-identity-pool=github \
    --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
    --attribute-condition="assertion.repository_owner == '${GH_OWNER}'" \
    --project $PROJECT_ID
```

`attribute-condition` 의 `repository_owner == '${GH_OWNER}'` 가 핵심 보안 장치입니다. 이게 없으면 같은 issuer 의 다른 GitHub 사용자도 토큰으로 GCP 에 들어올 수 있습니다.

### 6-6. 본인 fork repo 가 SA 를 impersonate 할 수 있도록 바인딩

```bash
gcloud iam service-accounts add-iam-policy-binding $CI_SA \
    --role=roles/iam.workloadIdentityUser \
    --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${GH_OWNER}/${GH_REPO}" \
    --project $PROJECT_ID
```

이 한 줄이 "이 SA 는 **이 특정 GitHub repo** 의 워크플로우에서만 impersonate 가능하다" 를 박는 부분입니다.

### 6-7. WIF Provider 의 전체 리소스 경로 확인

GitHub Variables 에 넣을 값입니다.

```bash
echo "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/providers/github-provider"
```

## 7단계 — GitHub repo Variables 등록

본인 fork 의 GitHub 페이지로 가서 **Settings → Secrets and variables → Actions → Variables** 탭에서 7 개 추가합니다 (Secrets 가 아니라 Variables).

| 이름 | 값 (예시) |
|---|---|
| `GCP_PROJECT` | `your-gcp-project-id` |
| `GCP_REGION` | `us-central1` |
| `PIPELINE_ROOT` | `gs://<your-project>-vertex-pipelines/pipeline-root` |
| `AR_REPO` | `vertex-ci-images` |
| `KFP_HOST` | `https://us-kfp.pkg.dev/<your-project>/kfp-templates` |
| `WIF_PROVIDER` | 6-7 명령이 출력한 전체 경로 |
| `WIF_SERVICE_ACCOUNT` | `vertex-ci@<your-project>.iam.gserviceaccount.com` |

## 8단계 — 첫 워크플로우 트리거

`main` 으로 빈 커밋을 한 번 푸시하면 워크플로우가 자동으로 실행됩니다.

```bash
git commit --allow-empty -m "trigger ci"
git push origin main
```

또는 GitHub repo 의 **Actions** 탭 → `03-ci-cd` 워크플로우 → **Run workflow** 버튼으로 수동 실행도 가능합니다.

## 9단계 — 결과 확인

Actions 탭에서 흐름이 이렇게 진행되는 것을 봅니다:

1. `Authenticate to Google Cloud (WIF)` — 통과 못 하면 6-5/6-6 의 WIF 바인딩이 잘못된 것
2. `Resolve per-component image tags (last-touch SHA)` — 각 컴포넌트의 태그가 출력되는지 확인
3. `Build & push only changed components` — 변경된 컴포넌트만 빌드. 첫 실행이면 세 개 다 빌드, 그 이후는 변경된 것만. 통과 못 하면 6-3 의 AR 저장소 또는 SA 의 `roles/artifactregistry.writer` 권한 누락
4. `Compile pipeline with per-component tags` — 컴포넌트별 태그가 YAML 에 잘 박혔는지 로그 확인
5. `Upload pipeline template to KFP registry` — 통과하면 콘솔의 템플릿 화면에 새 버전이 등록됨

이후 **Vertex AI 콘솔 → 파이프라인 → 템플릿** 으로 이동해 `ci-cd-cifar10` 템플릿을 클릭. 등록된 버전 목록에서 방금 푸시한 git SHA 또는 `latest` 태그를 선택하고 **"실행 만들기"** 를 누릅니다.

런타임 구성 화면에서 컴퓨팅 스펙과 GPU 사용 여부를 직접 선택할 수 있습니다:

| 파라미터 | CPU 학습 | T4 GPU 1대 학습 |
|---|---|---|
| `cpu_train` | `4` | `4` |
| `memory_train` | `16G` | `16G` |
| `train_accelerator_type` | `NVIDIA_TESLA_T4` (그대로) | `NVIDIA_TESLA_T4` |
| `train_accelerator_count` | `0` | `1` |

`train_accelerator_count=0` 이면 GPU 미할당 (CUDA 베이스 이미지여도 자동 CPU fallback). `1` 로 바꾸면 T4 1 개가 붙습니다. T4 학습은 콜드 스타트 포함 5–10 분 추가될 수 있고, CPU 실행은 콜드 스타트만 1–3 분 정도입니다. 첫 실행은 이미지 pull + CIFAR-10 다운로드까지 포함되어 15–20 분 정도 걸립니다.

## 자주 막히는 지점 모음

**`storage.objects.get` / `create` 권한 에러**
2단계 후반부에서 기본 Compute SA 에 버킷 권한 부여를 빼먹은 경우. 파이프라인 실행 SA (콘솔에서 SA 를 명시 안 하면 기본 Compute SA 가 자동 선택) 에도 따로 권한이 필요합니다. `gcloud storage buckets add-iam-policy-binding` 명령을 빼먹지 않았는지 확인.

**`Permission 'iam.serviceAccounts.getAccessToken' denied`**
WIF principalSet 의 `${GH_OWNER}/${GH_REPO}` 가 본인 fork 와 정확히 일치하지 않으면 발생. 대소문자, 오타, 그리고 **fork 한 계정 vs 원본 계정** 을 혼동하지 않았는지 확인.

**`IAM Service Account Credentials API has not been used in project ... or it is disabled`**
2-2 의 API 활성화 명령에서 `iamcredentials.googleapis.com` 이 빠진 경우. WIF 가 OIDC 토큰을 받아 SA 를 impersonate 하려면 이 API 가 켜져 있어야 합니다. `gcloud services enable iamcredentials.googleapis.com --project $PROJECT_ID` 한 번 돌리고, 1–2 분 propagation 후 워크플로우 Re-run.

**이미지 pull 실패 (`ErrImagePull` / `Schema 1 deprecated`)**
챕터 01 의 busybox 처럼 manifest 가 deprecated 된 외부 이미지 참조 시 발생. 본인이 빌드한 이미지를 쓰면 이 문제는 안 생깁니다. 챕터 03 은 본인 빌드 이미지만 쓰니 안전.

**`Invalid image URI` (Vertex AI 제출 단계)**
이미지 호스트가 Vertex AI 의 허용 목록에 없을 때 발생. `*-docker.pkg.dev/<project>`, Docker Hub (`busybox:stable` 같이 prefix 없는 형식) 만 허용됩니다. `mirror.gcr.io` 같은 호스트는 reject 됩니다.

**`RESOURCE_EXHAUSTED: ... custom_model_training_nvidia_t4_gpus exceed quota limits`**
콘솔에서 `train_accelerator_count=1` 로 학습 잡을 제출했을 때 발생. 핵심은 **GPU 쿼터가 사실상 세 종류로 나뉘어 있고 서로 별개로 운영된다** 는 점입니다.

| 쿼터 | 용도 | 신규 프로젝트 디폴트 |
|---|---|---|
| `compute.googleapis.com/NVIDIA_T4_GPUS` | GCE 일반 VM 용 | 1 (T4) |
| `aiplatform.googleapis.com/custom_model_training_nvidia_t4_gpus` | **Vertex AI 학습 잡** | **0** ← 이 에러의 주범 |
| `aiplatform.googleapis.com/custom_model_serving_nvidia_t4_gpus` | Vertex AI 모델 서빙 | 1 |

`SETUP.md` 의 quota 확인 명령은 첫 번째(GCE) 만 보여줍니다. 학습 잡은 두 번째를 봅니다. 즉 GCE T4 가 1 이라도 Vertex AI training T4 는 별도로 0 일 수 있습니다.

**즉시 해결**: 콘솔의 "실행 만들기" 에서 `train_accelerator_count=0` 으로 재실행. CPU 로 학습됩니다 (CUDA 베이스 이미지여도 자동 fallback). CIFAR-10 + SimpleCNN 은 작아서 CPU 로 5–8 분 안에 끝나고 데모 의도에는 충분.

**GPU 학습이 정말 필요하면 — 쿼터 증가 신청**:

1. 콘솔로 이동 (본인 프로젝트 ID 로 자동 매핑됨):
   ```
   https://console.cloud.google.com/iam-admin/quotas?project=<PROJECT_ID>
   ```
2. 상단 Filter 에 `Custom model training Nvidia T4` 입력
3. 결과 목록에서 본인 리전(예: `us-central1`) 행 체크
4. 우상단 **Edit Quotas** → 새 한도 `1` 입력 + 사유 작성 (예: "demo training of small CNN for educational purposes")
5. 제출 후 1–24 시간 대기 (신규 계정은 보통 빠르게 승인)
6. 승인 후 콘솔에서 `train_accelerator_count=1` 로 재실행

**A100 같은 상위 GPU** 는 신규 프로젝트에서 모든 종류 쿼터가 0 으로 시작합니다. 같은 절차로 신청 가능하지만 승인이 더 까다롭습니다.

**워크플로우는 도는데 콘솔의 템플릿 목록에 안 보임**
프로젝트가 일치하는지, 그리고 콘솔의 **파이프라인 → 템플릿** 화면이 KFP repo 의 위치를 자동으로 잡는지 확인. 6-4 에서 `--location=us` 멀티 리전으로 만든 경우 대부분 자동 인식되지만, 단일 리전에 만들었다면 콘솔 좌측 상단 리전 셀렉터를 그 리전으로 맞춰야 보입니다.

**캐시가 없는데도 두 번째 실행이 너무 빠름**
KFP 가 입력이 같으면 캐시된 결과를 재사용합니다. 본인이 의도한 바가 아니면 콘솔의 "실행 만들기" 화면에서 캐시 옵션을 끄고 실행하세요.

**같은 commit 으로 워크플로우 재실행했는데 이미지 빌드가 모두 skip 됨**
이건 정상입니다. 모든 컴포넌트의 태그(=last-touch SHA) 가 이미 AR 에 푸시되어 있어 빌드를 생략한 것. 강제로 재빌드하려면 해당 컴포넌트 폴더에 의미 있는 변경(또는 빈 변경) 을 한 새 커밋이 필요합니다.

## 정리 / 다음 단계

여기까지 통과하면 핸즈온의 모든 챕터를 본인 환경에서 재현한 것입니다. 다음으로 시도해 볼 만한 것들:

- **GPU 학습 켜기/끄기**: 코드 수정 없이 콘솔의 "실행 만들기" 에서 `train_accelerator_count` 를 1로 두면 T4 1 대로 학습. 0으로 두면 CPU. 같은 템플릿 하나로 두 모드를 자유롭게 오갈 수 있습니다.
- **하이퍼파라미터 변경 후 재배포**: `pipeline.py` 의 `epochs`, `batch_size`, `lr` 기본값을 바꿔 커밋하거나, 그대로 두고 콘솔에서 매 실행마다 오버라이드.
- **컴포넌트 추가**: `inference` 컴포넌트를 추가해 모델을 받아서 단일 이미지에 대한 예측을 출력하도록 확장. 새 폴더에 `Dockerfile` + `main.py` 만 만들면 워크플로우의 monorepo 로직이 자동으로 인식해 빌드.
- **변경 영향 범위 실험**: 한 컴포넌트 폴더만 의미 있는 변경 후 push → Actions 로그에서 그 컴포넌트만 빌드되고 나머지는 `::notice::skip` 으로 건너뛰는 것을 확인.
- **PR 트리거 추가**: 현재는 main push 에만 트리거. PR 에서 빌드까지만 하고 템플릿 등록은 main 에서만 하도록 분리하면 더 안전한 GitOps 패턴이 됩니다.
