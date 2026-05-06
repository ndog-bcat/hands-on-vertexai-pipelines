# Cloud Shell 가이드 (CLI 에이전트용)

이 문서는 GCP Cloud Shell 환경에서 본 핸즈온을 처음부터 끝까지 진행하기 위한 **에이전트 친화 가이드** 입니다. 각 단계는 다음 형식으로 작성되어 있습니다:

- **Goal**: 이 단계가 달성하려는 결과
- **Command(s)**: 실행할 명령. `<...>` 은 사용자 입력으로 치환할 자리표시자
- **Expected**: 정상 동작 시 보이는 출력의 핵심 시그널
- **Verify**: 다음 단계로 가기 전 통과해야 하는 체크 명령
- **If fails**: 실패 시 진단 / 복구
- **Human required**: 사람이 브라우저나 GUI 에서 직접 해야 하는 단계 (에이전트는 사용자에게 알리고 대기)

에이전트는 각 Verify 가 통과한 뒤에만 다음 단계로 진행하세요. 모든 명령은 **idempotent** 하게 작성되어 있어 (안전하게 재실행 가능), 세션이 끊겨도 처음부터 다시 돌리면 됩니다.

---

## Phase 0 — Cloud Shell 환경 검증

세션을 새로 열었을 때 먼저 환경이 정상인지 확인합니다.

### 0-1. Cloud Shell 안에서 돌고 있는지 확인

**Goal**: 본 가이드가 가정하는 환경(Cloud Shell) 인지 검증.

**Command**:
```bash
echo "CLOUD_SHELL=${CLOUD_SHELL:-not-set}, GOOGLE_CLOUD_SHELL=${GOOGLE_CLOUD_SHELL:-not-set}"
echo "USER=$USER, HOME=$HOME"
uname -a
```

**Expected**: `CLOUD_SHELL=true` 또는 `GOOGLE_CLOUD_SHELL=true`. `$HOME` 이 `/home/<user>`. uname 은 Debian 기반 Linux.

**Verify**:
```bash
[[ "${CLOUD_SHELL:-${GOOGLE_CLOUD_SHELL:-}}" == "true" ]] && echo OK || echo NOT_CLOUD_SHELL
```

**If fails**: Cloud Shell 이 아니라면 이 가이드는 적합하지 않음. 로컬용 가이드 `HANDS_ON.md` 를 사용. 또는 https://shell.cloud.google.com 에서 새 Cloud Shell 세션을 열고 다시 시작.

### 0-2. 사전 설치 도구 버전 확인

**Goal**: gcloud / git / docker / python / gh 가 모두 사용 가능한지 확인.

**Command**:
```bash
for cmd in gcloud git docker python3 gh; do
  if command -v $cmd >/dev/null 2>&1; then
    printf '%-10s OK  %s\n' "$cmd" "$($cmd --version 2>&1 | head -1)"
  else
    printf '%-10s MISSING\n' "$cmd"
  fi
done
```

**Expected**: 5 개 모두 `OK`. Cloud Shell 디폴트 이미지에 모두 포함되어 있습니다.

**If fails**: 어느 하나라도 MISSING 이면 Cloud Shell 이미지가 비표준 상태. `gcloud components install <component>` 로 보강하거나, Cloud Shell 의 "Restart" 메뉴로 디폴트 이미지로 재시작.

---

## Phase 1 — uv 설치

**Goal**: 파이썬 의존성 매니저 `uv` 설치. Cloud Shell 의 `$HOME` 은 영구 보존되므로 한 번만 설치하면 됩니다.

### 1-1. 이미 설치되어 있는지 확인

**Command**:
```bash
if command -v uv >/dev/null 2>&1; then
  echo "uv $(uv --version) already installed"
else
  echo "uv missing — proceed to 1-2"
fi
```

**If already installed**: Phase 1 종료. Phase 2 로.

### 1-2. uv 설치

**Command**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

**Expected**: 설치 로그 + `installed uv` 메시지. 이후 `uv` 명령이 PATH 에 들어옴.

**Verify**:
```bash
uv --version
```

→ `uv 0.x.x` 출력되어야 함.

**If fails**:
- 네트워크 오류: Cloud Shell 의 외부 인터넷 접근 일시 장애. 1–2 분 후 재시도.
- PATH 미반영: `source $HOME/.local/bin/env` 를 다시 실행하거나 새 셸 열기.

### 1-3. 다음 세션에서도 자동 로드되도록 `.bashrc` 에 등록

**Command**:
```bash
if ! grep -q '/.local/bin/env' ~/.bashrc; then
  echo 'source $HOME/.local/bin/env' >> ~/.bashrc
  echo 'added uv env to .bashrc'
else
  echo 'uv env already in .bashrc'
fi
```

---

## Phase 2 — GitHub 인증

**Goal**: `gh` CLI 로 GitHub 인증. PAT 를 채팅에 노출시키지 않고 OAuth 디바이스 플로우로 처리.

### 2-1. 이미 인증되어 있는지 확인

**Command**:
```bash
gh auth status 2>&1 | head -5
```

**Expected (인증됨)**: `✓ Logged in to github.com as <username>`. → Phase 2 종료.

**Expected (미인증)**: `You are not logged into any GitHub hosts`. → 2-2 로.

### 2-2. 디바이스 플로우 로그인

**Human required**: 브라우저에서 one-time code 입력 필요.

**Command**:
```bash
gh auth login --hostname github.com --git-protocol https --web
```

**Expected**: `! First copy your one-time code: XXXX-XXXX` 메시지와 `Press Enter to open github.com in your browser...` 프롬프트. 사용자가 표시된 코드를 별도 브라우저 탭에서 https://github.com/login/device 에 입력하면 인증 완료.

**Agent action**: 사용자에게 표시된 8자리 코드를 입력하라고 안내하고, `gh auth status` 가 통과할 때까지 대기.

**Verify**:
```bash
gh auth status 2>&1 | grep -E 'Logged in to github.com'
```

**If fails**:
- 타임아웃: `gh auth login` 재시도
- 토큰 권한 부족: 재로그인 시 `--scopes "repo,workflow"` 추가

---

## Phase 3 — 파이썬 의존성 설치

**Command**:
```bash
uv sync
```

**Expected**: `Resolved N packages` + `Installed N packages`. `.venv/` 디렉터리가 생성됨 (이것도 `$HOME` 안이라 영구 보존).

**Verify**:
```bash
uv run python -c "from kfp import dsl; from google.cloud import aiplatform; print('OK')"
```

→ `OK` 출력.

---

## Phase 4 — GCP 인증 & 프로젝트 설정

**Goal**: gcloud 가 본인 GCP 프로젝트를 가리키게 하고, ADC 가 quota project 를 알게 함.

### 4-1. 현재 인증 상태 확인

**Command**:
```bash
gcloud auth list --filter=status:ACTIVE --format='value(account)'
```

**Expected**: 본인 Google 계정 이메일 한 줄. Cloud Shell 은 세션 시작 시 자동으로 인증되어 있음.

**If fails (출력 비어 있음)**: 첫 gcloud 명령 시 콘솔 상단에 "Authorize Cloud Shell" 팝업이 떴어야 함. 어느 명령이든 한 번 더 실행해 팝업을 띄우고 **Authorize** 클릭.

### 4-2. 프로젝트 ID 결정 (Human required)

**Agent action**: 본인 프로젝트 ID 를 묻고 환경변수로 보관.

**Command**:
```bash
gcloud projects list --format='table(projectId,name)' | head -20
```

→ 위 목록에서 사용할 프로젝트 ID 확인.

```bash
read -p "GCP project ID to use: " PROJECT_ID
export PROJECT_ID
export REGION=us-central1
export BUCKET=${PROJECT_ID}-vertex-pipelines
echo "PROJECT_ID=$PROJECT_ID REGION=$REGION BUCKET=$BUCKET"
```

### 4-3. 활성 프로젝트 / quota 프로젝트 지정

**Command**:
```bash
gcloud config set project $PROJECT_ID
gcloud auth application-default set-quota-project $PROJECT_ID
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
echo "PROJECT_NUMBER=$PROJECT_NUMBER"
```

**Verify**:
```bash
[[ "$(gcloud config get-value project)" == "$PROJECT_ID" ]] && echo OK || echo MISMATCH
[[ -n "$PROJECT_NUMBER" ]] && echo OK || echo NO_PROJECT_NUMBER
```

### 4-4. 환경변수 영구화

**Goal**: 다음 세션에도 `PROJECT_ID` 등이 자동 export 되도록.

**Command**:
```bash
RC_BLOCK=$(cat <<EOF
# === hands-on-vertexai-pipelines ===
export PROJECT_ID=$PROJECT_ID
export PROJECT_NUMBER=$PROJECT_NUMBER
export REGION=$REGION
export BUCKET=$BUCKET
export GH_OWNER=$GH_OWNER
export GH_REPO=$GH_REPO
export GCP_PROJECT=\$PROJECT_ID
export GCP_REGION=\$REGION
export PIPELINE_ROOT=gs://\$BUCKET/pipeline-root
# ===================================
EOF
)
if ! grep -q 'hands-on-vertexai-pipelines' ~/.bashrc; then
  echo "$RC_BLOCK" >> ~/.bashrc
  echo "appended to .bashrc"
else
  echo ".bashrc already has the block (skipping)"
fi
source ~/.bashrc
```

**Verify**:
```bash
[[ -n "$GCP_PROJECT" && -n "$PIPELINE_ROOT" ]] && echo OK || echo NOT_EXPORTED
```

---

## Phase 5 — GCP API 활성화

**Goal**: 핸즈온이 사용하는 6 개 API 모두 enable.

### 5-1. 일괄 활성화

**Command**:
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

**Expected**: 마지막 줄 `Operation "operations/..." finished successfully` 또는 이미 켜져 있어 빠르게 통과.

**Verify**:
```bash
gcloud services list --enabled --project $PROJECT_ID \
  --format='value(config.name)' \
  | grep -E '^(aiplatform|storage|compute|iamcredentials|iam|artifactregistry)\.googleapis\.com$' \
  | sort | uniq | wc -l
```

→ `6` 출력.

**If fails (count < 6)**:
- 네트워크/권한 문제로 일부만 enable. 위 명령을 재실행.
- 사용자가 프로젝트의 `serviceusage.services.enable` 권한이 없으면 프로젝트 owner 에게 요청.

---

## Phase 6 — Pipeline-root GCS 버킷

### 6-1. 버킷 생성

**Command**:
```bash
if gcloud storage buckets describe gs://$BUCKET --project $PROJECT_ID >/dev/null 2>&1; then
  echo "bucket gs://$BUCKET already exists"
else
  gcloud storage buckets create gs://$BUCKET --location=$REGION --project $PROJECT_ID
fi
```

**Verify**:
```bash
gcloud storage buckets describe gs://$BUCKET --format='value(name,location)' --project $PROJECT_ID
```

→ `<BUCKET> US-CENTRAL1` (또는 본인이 선택한 리전).

### 6-2. 기본 Compute SA 에 권한 부여 (필수)

**Goal**: 파이프라인 실행 SA(콘솔에서 별도 지정 안 하면 기본 Compute SA) 가 GCS 및 Vertex AI 메타데이터 저장소에 접근할 수 있게 함. 이 단계 빼먹으면 첫 제출에서 100% 실패함.

**Command**:
```bash
# 1. GCS 버킷 관리 권한
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/storage.objectAdmin" \
    --project $PROJECT_ID

# 2. Vertex AI 사용자 권한 (메타데이터 저장소 접근용)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/aiplatform.user" \
    --project $PROJECT_ID
```

**Verify**:
```bash
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten='bindings[].members' \
  --filter="bindings.members:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --format='value(bindings.role)' \
  | grep -E 'roles/storage.objectAdmin|roles/aiplatform.user'
```

→ 두 역할이 모두 출력되어야 함.

---

## Phase 7 — 챕터 01 검증 실행 (smoke test)

**Goal**: 환경 셋업이 끝까지 정상인지 가장 단순한 파이프라인으로 검증.

### 7-1. Direct-run 으로 컴파일 + 제출

**Command**:
```bash
cd $HOME/$GH_REPO
# 실행 전 환경변수가 현재 세션에 로드되어 있는지 확인
export GCP_PROJECT=$PROJECT_ID
export GCP_REGION=$REGION

uv run python 01-first-pipeline/01-direct-run.py 2>&1 | tee /tmp/01-run.log
```

**Expected**: 마지막 줄들에 `제출 완료 PipelineJob: ...` 와 `콘솔 URL: https://console.cloud.google.com/...`.

**Verify**:
```bash
grep -q '제출 완료 PipelineJob' /tmp/01-run.log && echo SUBMITTED || echo NOT_SUBMITTED
```

**If fails**:
- `storage.objects.get/create` 권한 에러 → 6-2 안 했음. 6-2 다시 실행.
- API 비활성 에러 → Phase 5 다시 실행.
- 다른 인증 에러 → `gcloud auth application-default print-access-token` 으로 토큰 발급 가능한지 확인.

### 7-2. (선택) 콘솔 URL 출력

**Command**:
```bash
grep '콘솔 URL' /tmp/01-run.log | tail -1
```

**Human action**: 출력된 URL 을 새 탭에서 열어 그래프가 도는 것을 확인 (5–7 분).

---

## Phase 8 — 챕터 02 (선택)

**Goal**: 데이터 공유 3 가지 방식을 각각 컴파일 + 제출.

### 8-1. 세 파일 모두 컴파일

**Command**:
```bash
cd $HOME/$GH_REPO
for f in 02-data-sharing/02-{gcs-string,artifact-io,gcs-fuse}.py; do
  uv run python "$f"
done
```

**Verify**:
```bash
ls -la 02-data-sharing/*.yaml | wc -l
```

→ `3` 출력.

### 8-2. 세 파이프라인 모두 제출

**Command**:
```bash
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

**Expected**: 각각 `제출 완료 PipelineJob: ...` + 콘솔 URL.

---

## Phase 9 — 챕터 03 CI/CD 셋업

여기서부터는 GitHub Actions 가 본인 GCP 프로젝트로 빌드/배포할 수 있도록 IAM 자원을 만드는 단계입니다.

### 9-1. CI 전용 서비스 계정 생성

**Command**:
```bash
if gcloud iam service-accounts describe vertex-ci@$PROJECT_ID.iam.gserviceaccount.com --project $PROJECT_ID >/dev/null 2>&1; then
  echo "SA vertex-ci already exists"
else
  gcloud iam service-accounts create vertex-ci \
      --display-name="Vertex AI CI runner" \
      --project $PROJECT_ID
fi
export CI_SA=vertex-ci@$PROJECT_ID.iam.gserviceaccount.com
echo "CI_SA=$CI_SA"
```

**Verify**:
```bash
gcloud iam service-accounts describe $CI_SA --project $PROJECT_ID --format='value(email)'
```

→ `vertex-ci@<PROJECT_ID>.iam.gserviceaccount.com`.

### 9-2. SA 에 프로젝트 역할 4 개 부여

**Command**:
```bash
for role in roles/aiplatform.user roles/artifactregistry.writer roles/storage.admin roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:$CI_SA" --role="$role" \
      --condition=None >/dev/null
  echo "granted $role"
done
```

**Verify**:
```bash
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten='bindings[].members' \
  --filter="bindings.members:$CI_SA" \
  --format='value(bindings.role)' | sort -u
```

→ 4 개 역할이 모두 출력되어야 함.

### 9-3. Pipeline-root 버킷에도 SA 권한 부여

**Command**:
```bash
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
    --member="serviceAccount:$CI_SA" \
    --role="roles/storage.objectAdmin" \
    --project $PROJECT_ID
```

### 9-4. Artifact Registry 저장소 두 개

**Command (Docker 이미지용)**:
```bash
if gcloud artifacts repositories describe vertex-ci-images --location=$REGION --project=$PROJECT_ID >/dev/null 2>&1; then
  echo "AR repo vertex-ci-images already exists"
else
  gcloud artifacts repositories create vertex-ci-images \
      --repository-format=docker \
      --location=$REGION \
      --project $PROJECT_ID
fi
```

**Command (KFP 템플릿용)**:
```bash
if gcloud artifacts repositories describe kfp-templates --location=us --project=$PROJECT_ID >/dev/null 2>&1; then
  echo "AR repo kfp-templates already exists"
else
  gcloud artifacts repositories create kfp-templates \
      --repository-format=kfp \
      --location=us \
      --project $PROJECT_ID
fi
```

**Verify**:
```bash
gcloud artifacts repositories list --project=$PROJECT_ID --format='table(name.basename(),format,location)'
```

→ 두 repo 모두 보여야 함 (`vertex-ci-images / DOCKER / us-central1`, `kfp-templates / KFP / us`).

### 9-5. Workload Identity Federation Pool 생성

**Command**:
```bash
if gcloud iam workload-identity-pools describe github --location=global --project=$PROJECT_ID >/dev/null 2>&1; then
  echo "WIF pool 'github' already exists"
else
  gcloud iam workload-identity-pools create github \
      --location=global \
      --display-name="GitHub Actions" \
      --project $PROJECT_ID
fi
```

### 9-6. WIF Provider 등록

**Command**:
```bash
if gcloud iam workload-identity-pools providers describe github-provider \
     --location=global --workload-identity-pool=github --project=$PROJECT_ID >/dev/null 2>&1; then
  echo "WIF provider 'github-provider' already exists"
else
  gcloud iam workload-identity-pools providers create-oidc github-provider \
      --location=global \
      --workload-identity-pool=github \
      --display-name="GitHub OIDC" \
      --issuer-uri="https://token.actions.githubusercontent.com" \
      --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
      --attribute-condition="assertion.repository_owner == '${GH_OWNER}'" \
      --project $PROJECT_ID
fi
```

**Note**: `attribute-condition` 의 `repository_owner` 가 본인 GitHub username 과 정확히 일치해야 함 (대소문자 포함).

### 9-7. 본인 fork repo ↔ SA 바인딩

**Command**:
```bash
gcloud iam service-accounts add-iam-policy-binding $CI_SA \
    --role=roles/iam.workloadIdentityUser \
    --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${GH_OWNER}/${GH_REPO}" \
    --project $PROJECT_ID
```

**Verify**:
```bash
gcloud iam service-accounts get-iam-policy $CI_SA --project $PROJECT_ID \
  --flatten='bindings[].members' \
  --filter="bindings.members:principalSet*${GH_OWNER}/${GH_REPO}" \
  --format='value(bindings.role)' \
  | grep -q 'roles/iam.workloadIdentityUser' && echo OK || echo MISSING
```

→ `OK` 출력.

### 9-8. Variables 입력에 쓸 값 모두 한 번에 출력

**Goal**: GitHub Variables 화면에 그대로 복붙할 7 줄을 생성.

**Command**:
```bash
cat <<EOF

──────── GitHub Variables (Settings → Secrets and variables → Actions → Variables) ────────
GCP_PROJECT           = $PROJECT_ID
GCP_REGION            = $REGION
PIPELINE_ROOT         = gs://$BUCKET/pipeline-root
AR_REPO               = vertex-ci-images
KFP_HOST              = https://us-kfp.pkg.dev/$PROJECT_ID/kfp-templates
WIF_PROVIDER          = projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-provider
WIF_SERVICE_ACCOUNT   = $CI_SA
─────────────────────────────────────────────────────────────────────────────────────────────

EOF
```

---

## Phase 10 — GitHub Variables 입력 (Human required)

**Goal**: 9-8 에서 출력한 7 개 값을 GitHub fork 의 Variables 탭에 등록.

**Human action**: 아래 URL 을 새 탭에서 열고 (Cloud Shell 에서는 우상단 점 3개 → "Restart in new tab" 또는 그냥 새 브라우저 탭) Variables 7 개를 등록.

```
https://github.com/<GH_OWNER>/<GH_REPO>/settings/variables/actions
```

**중요**:
- "Secrets" 탭이 아니라 **"Variables" 탭** 인지 확인
- 이름은 정확히 위 7 개 (대문자/언더스코어)
- 값은 9-8 출력 그대로 복붙

**Verify** (Variables 가 등록되었는지 셸에서 확인 — gh CLI 가능):
```bash
gh variable list --repo $GH_OWNER/$GH_REPO
```

→ 7 줄이 보여야 함. 누락된 게 있으면 다시 등록.

---

## Phase 11 — 첫 워크플로우 트리거

**Goal**: GitHub Actions 가 한 번 돌아 이미지 빌드 + 템플릿 등록까지 통과.

### 11-1. main 으로 빈 커밋 push

**Command**:
```bash
cd $HOME/$GH_REPO
git commit --allow-empty -m "trigger ci from cloud shell"
git push origin main
```

**Expected**: `[main XXXXXXX] trigger ci from cloud shell` + `* [new commit]` push 로그.

### 11-2. 워크플로우 실행 모니터링

**Command**:
```bash
sleep 5
gh run list --workflow 03-ci-cd --repo $GH_OWNER/$GH_REPO --limit 1
gh run watch --repo $GH_OWNER/$GH_REPO
```

**Expected**: 5 step 이 차례로 ✓ 표시 후 `Run succeeded`. 첫 실행은 5–10 분 소요.

**If fails (특정 step 빨갛게 끝남)**:
- `Authenticate to Google Cloud (WIF)` → 9-5/9-6/9-7 의 WIF 설정에 문제. 9-7 의 Verify 명령 다시 확인.
- `Build & push only changed components` → AR 권한 또는 Docker 빌드 자체. `gh run view --log` 으로 상세 로그 확인.
- `Upload pipeline template to KFP registry` → KFP repo 권한. 9-2 의 `roles/artifactregistry.writer` 부여 확인.

**Verify**:
```bash
gh run list --workflow 03-ci-cd --repo $GH_OWNER/$GH_REPO --limit 1 --json conclusion --jq '.[0].conclusion'
```

→ `success` 출력.

---

## Phase 12 — 콘솔에서 템플릿 실행 (Human required)

**Goal**: 등록된 KFP 템플릿을 콘솔에서 실제로 실행.

**Human action**: 아래 URL 새 탭에서 열기:

```
https://console.cloud.google.com/vertex-ai/pipelines/templates?project=<PROJECT_ID>
```

**클릭 순서**:
1. `ci-cd-cifar10` 클릭
2. `latest` 태그 버전 선택
3. 우상단 **실행 만들기** 클릭
4. 런타임 구성:
   - 출력 디렉터리: 자동 채워짐 (PIPELINE_ROOT)
   - `train_accelerator_count`: `0` (CPU 학습) 또는 `1` (T4 GPU, 쿼터 있어야 함)
   - 나머지 파라미터는 기본값
5. **제출** 클릭

첫 실행은 이미지 pull + CIFAR-10 다운로드 포함 15–20 분.

---

## 실패 시 빠른 점검표

각 Phase 가 idempotent 하므로 막힌 곳부터 다시 돌리면 됩니다. 흔한 막힘과 해결:

| 증상 | 가장 자주 막힌 단계 |
|---|---|
| `storage.objects.get/create` 에러 | Phase 6-2 (기본 Compute SA 권한) 중 Storage Admin 누락 |
| `Permission 'aiplatform.metadataStores.get' denied` | Phase 6-2 에서 `roles/aiplatform.user` 권한 부여 누락 |
| `KeyError: 'GCP_PROJECT'` | `GCP_PROJECT` 환경변수 미설정. Phase 7-1의 export 명령 확인 |
| `IAM Service Account Credentials API ... is disabled` | Phase 5 에서 `iamcredentials.googleapis.com` 빠뜨림 |
| `Permission 'iam.serviceAccounts.getAccessToken' denied` | Phase 9-7 의 `${GH_OWNER}/${GH_REPO}` 가 fork 와 불일치 |
| 워크플로우의 `Authenticate ... WIF` 실패 | Phase 10 에서 Variables 가 Variables 탭이 아닌 Secrets 탭에 등록됨 |
| `RESOURCE_EXHAUSTED ... custom_model_training_nvidia_t4_gpus` | T4 학습 쿼터 0 (GCE 쿼터와 별개). `train_accelerator_count=0` 로 재실행하거나 콘솔에서 쿼터 신청 |
| `workerpool0-0 exited with status 1` / `No such file or directory` | GCS Fuse 동기화 지연 또는 권한 문제. Phase 6-2 권한 재확인 후 1-2분 뒤 재시도(Retry) |
| `Invalid image URI` | 이미지 호스트가 `mirror.gcr.io` 등 비허용 호스트. 본인 빌드 이미지 또는 Docker Hub 로 |

---

## 세션 재개 (다음 날, 새 Cloud Shell 세션)

`$HOME` 이 영구 보존이므로 아래만 하면 처음 상태로 돌아옵니다:

```bash
cd $HOME/$GH_REPO
git pull --ff-only
source ~/.bashrc   # PROJECT_ID 등 환경변수 자동 로드
gcloud config get-value project   # 프로젝트가 맞는지 확인
gh auth status                    # GitHub 인증 살아있는지 확인
```

uv 도, 클론한 repo 도, gcloud 인증도, GitHub 인증도 모두 살아있습니다. 셋업 다시 안 해도 됩니다.
