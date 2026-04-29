# 핸즈온 가이드 (Fork → 실행)

본인 GCP 프로젝트에 리소스를 만들고 본인 fork repo 와 연결합니다. 명령은 그대로 복붙하면 됩니다.

## 사전 준비

- 결제 계정이 연결된 본인 GCP 프로젝트
- GitHub 계정
- 로컬: `gcloud`, `git`, `python>=3.12`, `uv`

```bash
# gcloud 가 없으면
brew install --cask google-cloud-sdk
```

---

## 1. Fork & 클론

GitHub 에서 Fork 한 뒤:

```bash
git clone git@github.com:<YOUR_USERNAME>/<FORK_NAME>.git
cd <FORK_NAME>
uv sync
```

---

## 2. GCP 기초 셋업

```bash
export PROJECT_ID=<your-gcp-project-id>
export REGION=us-central1
export BUCKET=${PROJECT_ID}-vertex-pipelines
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
```

```bash
# 인증 (브라우저 두 번 열림)
gcloud auth login
gcloud auth application-default login
gcloud config set project $PROJECT_ID
gcloud auth application-default set-quota-project $PROJECT_ID
```

```bash
# API 활성화
gcloud services enable \
    aiplatform.googleapis.com \
    storage.googleapis.com \
    compute.googleapis.com \
    iamcredentials.googleapis.com \
    iam.googleapis.com \
    artifactregistry.googleapis.com \
    --project $PROJECT_ID
```

```bash
# 버킷 생성 + 기본 Compute SA 에 권한 부여 (실행 SA 가 GCS 접근하려면 필수)
gcloud storage buckets create gs://$BUCKET --location=$REGION --project $PROJECT_ID

gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/storage.objectAdmin" \
    --project $PROJECT_ID
```

---

## 3. 환경변수 export

```bash
export GCP_PROJECT=$PROJECT_ID
export GCP_REGION=$REGION
export PIPELINE_ROOT=gs://$BUCKET/pipeline-root
```

---

## 4. 챕터 01 — 첫 파이프라인

```bash
uv run python 01-first-pipeline/01-direct-run.py
```

출력된 **콘솔 URL** 클릭 → 그래프에서 `generate-data → process-data → notify` 가 차례로 ✅ 되는지 확인 (5–7 분).

---

## 5. 챕터 02 — 데이터 공유 3가지

```bash
# 컴파일
uv run python 02-data-sharing/02-gcs-string.py
uv run python 02-data-sharing/02-artifact-io.py
uv run python 02-data-sharing/02-gcs-fuse.py

# 제출
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

제출 후 출력된 콘솔 URL 세 개를 각각 열어서 노드 클릭 → **아티팩트** 탭 비교:
- `artifact-io` 만 Dataset 카드에 `num_rows`, `format` metadata 가 보임
- `gcs-string` / `gcs-fuse` 는 아티팩트 탭이 비어 있고 **파라미터** 탭에 경로 문자열만 보임

---

## 6. 챕터 03 — CI/CD 셋업

본인 fork 정보를 추가로 export:

```bash
export GH_OWNER=<your-github-username>
export GH_REPO=<your-fork-name>
```

### 6-1. CI 서비스 계정 + 권한

```bash
gcloud iam service-accounts create vertex-ci \
    --display-name "Vertex AI CI runner" \
    --project $PROJECT_ID

export CI_SA=vertex-ci@$PROJECT_ID.iam.gserviceaccount.com

for role in \
    roles/aiplatform.user \
    roles/artifactregistry.writer \
    roles/storage.admin \
    roles/iam.serviceAccountUser
do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:$CI_SA" --role="$role"
done

gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
    --member="serviceAccount:$CI_SA" \
    --role="roles/storage.objectAdmin" \
    --project $PROJECT_ID
```

### 6-2. Artifact Registry 저장소 두 개

```bash
# Docker 이미지용
gcloud artifacts repositories create vertex-ci-images \
    --repository-format=docker \
    --location=$REGION \
    --project $PROJECT_ID

# KFP 템플릿용 (location=us 권장 — 콘솔 인식이 안정적)
gcloud artifacts repositories create kfp-templates \
    --repository-format=kfp \
    --location=us \
    --project $PROJECT_ID
```

### 6-3. Workload Identity Federation

```bash
gcloud iam workload-identity-pools create github \
    --location=global \
    --display-name="GitHub Actions" \
    --project $PROJECT_ID

gcloud iam workload-identity-pools providers create-oidc github-provider \
    --location=global \
    --workload-identity-pool=github \
    --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
    --attribute-condition="assertion.repository_owner == '${GH_OWNER}'" \
    --project $PROJECT_ID

gcloud iam service-accounts add-iam-policy-binding $CI_SA \
    --role=roles/iam.workloadIdentityUser \
    --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${GH_OWNER}/${GH_REPO}" \
    --project $PROJECT_ID
```

WIF Provider 경로 확인 (7단계의 `WIF_PROVIDER` 값):

```bash
echo "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/providers/github-provider"
```

---

## 7. GitHub Variables 등록

본인 fork → **Settings → Secrets and variables → Actions → Variables 탭** (Secrets 가 아님). 7개 추가:

| 이름 | 값 |
|---|---|
| `GCP_PROJECT` | `<your-project-id>` |
| `GCP_REGION` | `us-central1` |
| `PIPELINE_ROOT` | `gs://<your-project>-vertex-pipelines/pipeline-root` |
| `AR_REPO` | `vertex-ci-images` |
| `KFP_HOST` | `https://us-kfp.pkg.dev/<your-project>/kfp-templates` |
| `WIF_PROVIDER` | 6-3 마지막 명령의 출력 |
| `WIF_SERVICE_ACCOUNT` | `vertex-ci@<your-project>.iam.gserviceaccount.com` |

---

## 8. 첫 워크플로우 트리거

```bash
git commit --allow-empty -m "trigger ci"
git push origin main
```

또는 Actions 탭 → `03-ci-cd` → **Run workflow**.

---

## 9. 워크플로우 통과 확인

GitHub repo → **Actions 탭** → 가장 최근 `03-ci-cd` 실행 클릭 → 5 step 이 모두 ✅ 인지 확인:

1. Authenticate to Google Cloud (WIF)
2. Resolve per-component image tags (last-touch SHA)
3. Build & push only changed components
4. Compile pipeline with per-component tags
5. Upload pipeline template to KFP registry

5단계까지 통과하면 GCP 콘솔로 이동.

---

## 10. 콘솔에서 템플릿 실행 (수동)

CI 는 **템플릿 등록까지만** 합니다. 실제 실행은 본인이 콘솔에서 시작합니다.

### 10-1. 템플릿이 올라왔는지 확인

```
https://console.cloud.google.com/vertex-ai/pipelines/templates?project=<PROJECT_ID>
```

좌측 메뉴 **에이전트 플랫폼 → 파이프라인 → 템플릿** 으로 들어가도 됨. 리전 셀렉터(좌상단) 가 `us-central1` 인지 확인. `ci-cd-cifar10` 항목이 보이고, 클릭하면 버전 목록(태그: `latest`, `<git-sha>`)이 나옵니다.

### 10-2. 실행 만들기

`ci-cd-cifar10` → 원하는 버전(보통 `latest`) 선택 → 우상단 **실행 만들기** 클릭.

런타임 구성 화면에서:

- **출력 디렉터리**: 기본값 그대로 두면 `PIPELINE_ROOT` Variable 값이 채워짐
- **파라미터**: 아래 표에 맞춰 선택

| 파라미터 | CPU 학습 | T4 GPU 학습 |
|---|---|---|
| `train_accelerator_count` | `0` | `1` |
| `cpu_train` / `memory_train` | `4` / `16G` | `4` / `16G` |
| `epochs` | `3` | `3` |

- **실패 정책**: "한 단계가 실패하는 즉시 이 실행 실패" 권장
- **캐시**: 첫 실행은 끔, 이후 재실행은 켜면 빠름

우하단 **제출** 클릭.

### 10-3. 실행 모니터링

제출 직후 자동으로 실행 상세 화면으로 이동. 그래프에서 노드를 클릭하면 우측 패널에:

- **로그** 탭 — Cloud Logging 의 실시간 stdout/stderr
- **노드 세부정보** 탭 — duration, 입력/출력 파라미터
- **아티팩트** 탭 — `Output[Dataset|Model|Metrics]` 카드

첫 실행은 이미지 pull + CIFAR-10 다운로드 포함 **15–20 분**. 두 번째부터는 캐시 + 이미지 cached 로 더 빠름.

### 10-4. 메트릭 확인

`evaluation` 노드 → **아티팩트** 탭 → `metrics` 카드 클릭 → `accuracy` 값 (CIFAR-10 SimpleCNN 기준 0.55–0.65 정도가 정상).

---

## 자주 막히는 지점

**`storage.objects.get` / `create` 권한 에러**
2단계의 기본 Compute SA 버킷 권한 부여를 빼먹은 경우. 해당 명령 다시 실행.

**`Permission 'iam.serviceAccounts.getAccessToken' denied`**
WIF 바인딩의 `${GH_OWNER}/${GH_REPO}` 가 fork 와 정확히 일치 안 함. 대소문자/오타 확인.

**`IAM Service Account Credentials API ... is disabled`**
2단계 API 활성화에서 `iamcredentials.googleapis.com` 누락. 다시 enable.

**`Invalid image URI`**
Vertex AI 가 허용하는 호스트만: `*-docker.pkg.dev/<project>`, Docker Hub (prefix 없는 형식). `mirror.gcr.io` 등은 reject.

**`RESOURCE_EXHAUSTED: ... custom_model_training_nvidia_t4_gpus`**
Vertex AI 학습용 GPU 쿼터가 0 (GCE T4 쿼터와 별개). **즉시 해결**: 콘솔에서 `train_accelerator_count=0` 으로 재실행. **GPU 가 필요하면**: 아래 절차로 쿼터 신청.

GPU 쿼터 신청:
1. `https://console.cloud.google.com/iam-admin/quotas?project=<PROJECT_ID>`
2. Filter: `Custom model training Nvidia T4`
3. 본인 리전 행 체크 → **Edit Quotas** → 한도 `1` 입력
4. 사유 (그대로 복붙):
   ```
   Hands-on learning project for Vertex AI Pipelines. Need 1 T4 in us-central1 to run a small CNN training job (under 10 minutes) end-to-end.
   ```
5. 제출 후 1–24시간 대기 → 승인 후 `train_accelerator_count=1` 로 재실행

**콘솔 템플릿 목록에 안 보임**
6-2 에서 KFP repo 를 `--location=us` 로 만들었는지 확인. 단일 리전에 만들었다면 콘솔 좌상단 리전 셀렉터를 맞춰야 함.

**같은 commit 재실행 시 이미지 빌드 모두 skip**
정상 동작. 모든 컴포넌트 태그가 이미 AR 에 있음. 강제 재빌드는 해당 폴더에 새 커밋 필요.

---

## 콘솔에서 직접 해야 하는 작업 모음

명령어로 자동화되지 않고 **반드시 웹 UI 에서 직접 클릭** 해야 하는 항목들:

| # | 위치 | 할 일 |
|---|---|---|
| 1 | GitHub repo → Settings → Secrets and variables → Actions → **Variables 탭** | 7 개 Variable 입력 (7단계) |
| 2 | (필요 시) GCP 콘솔 → IAM & Admin → **Quotas** | GPU 학습 쿼터 신청 (트러블슈팅 절) |
| 3 | GitHub repo → **Actions 탭** | 워크플로우 5 step 통과 확인 (9단계) |
| 4 | GCP 콘솔 → Vertex AI → **파이프라인 → 템플릿** | 등록된 템플릿 확인 + "실행 만들기" (10-1, 10-2) |
| 5 | Vertex AI → 파이프라인 → **실행** | 그래프 노드 클릭 → 로그 / 아티팩트 / 메트릭 확인 (10-3, 10-4) |

CI 는 **템플릿을 만들어 등록만 합니다.** 누가, 언제, 어떤 파라미터로 실행할지는 사람이 결정 — 이 분리가 운영에서 중요한 이유는 동일 코드를 dev/staging/prod 서로 다른 파라미터로 돌리거나 PR 리뷰어 승인 게이트를 추가하기 위해서입니다.

---

## 다음 단계

- **GPU 토글**: 콘솔에서 `train_accelerator_count` 0/1 만 바꿔서 같은 템플릿으로 두 모드 비교
- **하이퍼파라미터 변경**: `pipeline.py` 의 `epochs/batch_size/lr` 기본값 수정 후 commit
- **컴포넌트 추가**: 새 폴더에 `Dockerfile` + `main.py` 만들면 워크플로우가 자동 인식
- **변경 영향 실험**: 한 컴포넌트만 수정 후 push → Actions 로그에서 나머지가 `::notice::skip` 되는 것 확인
