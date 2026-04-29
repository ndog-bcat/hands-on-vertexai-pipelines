# 아키텍처 — push 한 줄에서 파이프라인 실행까지 일어나는 모든 일

이 문서는 챕터 03 의 CI/CD 시스템과 Vertex AI Pipelines 가 내부적으로 어떻게 동작하는지를 다섯 장의 다이어그램으로 설명합니다.

각 다이어그램은 독립적으로 읽어도 되지만, 이어서 보면 "내가 `git push` 한 한 줄의 변경이 GitHub Actions 빌드 → Artifact Registry 업로드 → KFP 템플릿 등록 → 사용자가 콘솔에서 "실행 만들기" → 워커 VM 위 컨테이너 실행 → 산출물이 GCS / ML Metadata / Cloud Logging 으로 분리 저장 → 콘솔의 그래프/카드/로그 탭" 까지 어떻게 흘러가는지의 전체 그림이 됩니다.

다섯 장의 구성:

1. **CI/CD 전체 흐름** — push 부터 템플릿 등록까지
2. **WIF 토큰 교환** — `auth@v2` 한 줄 안에서 일어나는 3-leg OIDC 플로우
3. **Monorepo 빌드 결정** — 변경된 컴포넌트만 빌드하는 분기 로직
4. **콘솔 실행 시 Vertex AI 내부 흐름** — control plane → 워커 fleet → ML Metadata
5. **워커 컨테이너 내부의 데이터/로그/메타데이터 분배** — FUSE / Cloud Logging / ML Metadata

---

## ① CI/CD 전체 흐름 — push 부터 템플릿 등록까지

```
┌────────────┐           ┌──────────────────┐
│ Developer  │  git push │ GitHub repo      │
│  (local)   │──────────>│ silverstar0727/  │
└────────────┘  ec697b8  │ hands-on-vertex… │
                         └────────┬─────────┘
                                  │ push 이벤트, paths 매칭
                                  │   • 03-ci-cd/**
                                  │   • .github/workflows/03-ci-cd.yml
                                  │   • pyproject.toml / uv.lock
                                  ▼
                ┌──────────────────────────────────────────┐
                │     GitHub Actions runner (ubuntu)       │
                │                                          │
                │  ① actions/checkout@v4 (fetch-depth=0)   │
                │     └─ git clone — 전체 history          │
                │        (last-touch SHA 검색에 필요)       │
                │                                          │
                │  ② google-github-actions/auth@v2  ───────┼──────┐
                │     └─ WIF 토큰 교환 (다이어그램 ② 참조)  │      │
                │                                          │      │
                │  ③ Resolve per-component tags            │      │
                │     for comp in (data-prep, train, eval):│      │
                │       SHA = `git log -1 --format=%h \    │      │
                │              -- 03-ci-cd/$comp/`         │      │
                │     → DATA_PREP_TAG=abc1234              │      │
                │       TRAIN_TAG    =def5678              │      │
                │       EVAL_TAG     =abc1234              │      │
                │                                          │      │
                │  ④ Build & push (다이어그램 ③ 참조)       │──┐   │
                │                                          │  │   │
                │  ⑤ uv run python pipeline.py             │  │   │
                │     (환경변수로 SHA 주입)                  │  │   │
                │     → ci-cd-pipeline.yaml (KFP IR)       │  │   │
                │                                          │  │   │
                │  ⑥ uv run python upload_template.py      │  │   │
                │     = kfp.registry.RegistryClient        │──┼─┐ │
                │       .upload_pipeline(...)              │  │ │ │
                └──────────────────────────────────────────┘  │ │ │
                                                              │ │ │
                                  ▼ (인증된 단기 토큰)         │ │ │
                                                              │ │ │
   ┌────────────────────────────────────────────────────┐    │ │ │
   │            GCP project: test-gcp-490616            │    │ │ │
   │                                                    │    │ │ │
   │  Artifact Registry (Docker)  ◄──────────────────── │────┘ │ │
   │  us-central1-docker.pkg.dev/                       │      │ │
   │   test-gcp-490616/vertex-ci-images/                │      │ │
   │   ├── data-preparation:abc1234   (push 또는 skip)   │      │ │
   │   ├── train:def5678               (push 또는 skip) │      │ │
   │   └── evaluation:abc1234         (push 또는 skip)   │      │ │
   │                                                    │      │ │
   │  Artifact Registry (KFP) ◄──────────────────────── │──────┘ │
   │  us-kfp.pkg.dev/                                   │        │
   │   test-gcp-490616/test-registry/                   │        │
   │   └── ci-cd-cifar10                                │        │
   │       ├── tag: latest                              │        │
   │       └── tag: ec697b8                             │        │
   │                                                    │        │
   │  IAM (배경에서 인증/인가 처리)  ◄────────────────── │────────┘
   │   • SA: vertex-ci@…                                │
   │   • WIF Pool: github + provider github-provider    │
   └────────────────────────────────────────────────────┘
                            │
                            ▼
                  ┌─────────────────────────┐
                  │ Vertex AI Console UI    │
                  │ "파이프라인 → 템플릿"     │
                  │ 사용자가 직접 클릭 후    │
                  │ "실행 만들기"             │
                  │ → 다이어그램 ④ 로        │
                  └─────────────────────────┘
```

---

## ② WIF 토큰 교환 (3-leg OIDC) — `auth@v2` 한 줄 안에서 일어나는 일

```
┌───────────────────────┐         ┌───────────────────────────────┐
│ GitHub Actions runner │         │ GitHub OIDC token issuer      │
│                       │         │ token.actions.githubusercontent│
│ permissions:          │         │       .com                    │
│   id-token: write     │         └───────────────┬───────────────┘
└──────────┬────────────┘                         │
           │ (a) 환경변수 ACTIONS_ID_TOKEN_REQUEST_URL/TOKEN 으로
           │     OIDC 토큰 요청                                ▲
           │ ─────────────────────────────────────────────────│
           │                                                  │
           │ (b) JWT 토큰 응답                                 │
           │     payload:                                     │
           │       iss = https://token.actions.…              │
           │       sub = repo:silverstar0727/hands-on-…:ref:… │
           │       repository = silverstar0727/hands-on-…     │
           │       repository_owner = silverstar0727          │
           │ ◄────────────────────────────────────────────────│
           │
           │ (c) 받은 JWT 를 Google STS 에 제출
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ Google STS  (sts.googleapis.com/v1/token)                        │
│                                                                  │
│  검증 항목:                                                       │
│   • JWT 서명 (GitHub 의 JWKS 로 검증)                              │
│   • iss = expected issuer                                        │
│   • aud = WIF provider 가 기대하는 값                              │
│   • attribute-condition:                                         │
│      assertion.repository_owner == 'silverstar0727'  ← 통과 필수  │
│   • attribute-mapping 으로 JWT claim → google attribute 변환      │
│      assertion.repository → attribute.repository                 │
│                                                                  │
│  → 외부 자격 증명을 google.federated 형태의                        │
│    "principal://" identity 로 변환                                │
└──────────────────────────────┬───────────────────────────────────┘
                               │ (d) federated token 반환
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ IAM Credentials API                                              │
│ iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/      │
│   vertex-ci@test-gcp-490616.iam.gserviceaccount.com:              │
│   generateAccessToken                                            │
│                                                                  │
│  검증:                                                            │
│   • 호출자(federated identity) 가 SA 에 대해                       │
│     roles/iam.workloadIdentityUser 가지는지                       │
│     ↑ 6-6 단계의 add-iam-policy-binding 이 한 일                  │
│     member: principalSet://…/attribute.repository/                │
│             silverstar0727/hands-on-vertexai-pipelines             │
│                                                                  │
│  → SA 의 단기 OAuth2 access token (1h) 발급                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │ (e) access token 반환
                               ▼
            ┌─────────────────────────────────────────┐
            │ runner 의 GOOGLE_APPLICATION_CREDENTIALS │
            │ 환경에 ADC 로 주입됨                       │
            │ → 이후 모든 gcloud / SDK 호출이 이 토큰   │
            │   으로 인증 (docker push / kfp upload)    │
            └─────────────────────────────────────────┘
```

---

## ③ Monorepo 빌드 결정 (변경된 컴포넌트만 빌드)

```
입력:  HEAD commit = ec697b8
       last-touch SHA per dir:
         03-ci-cd/data-preparation/  →  abc1234
         03-ci-cd/train/             →  def5678   (이번 PR 에서 변경)
         03-ci-cd/evaluation/        →  abc1234

──────────────────────────────────────────────────────────────────
 for comp in (data-preparation, train, evaluation):
──────────────────────────────────────────────────────────────────

      ┌────────────────────────────────────┐
      │ tag = TAG_MAP[$comp]               │
      │ image = $IMAGE_REGISTRY/$comp:$tag │
      └─────────────┬──────────────────────┘
                    │
                    ▼
      ┌────────────────────────────────────┐
      │ gcloud artifacts docker tags list  │
      │   $image_path --filter=tag=$tag    │
      └─────────────┬──────────────────────┘
                    │
            ┌───────┴────────┐
            │                │
       있음 │                │ 없음
            ▼                ▼
   ┌─────────────────┐  ┌─────────────────────────────────┐
   │ ::notice::skip  │  │ docker buildx build --push      │
   │ <image>:<tag>   │  │   --tag $image                  │
   │ already exists  │  │   03-ci-cd/$comp                │
   └─────────────────┘  │ → AR 에 새 manifest 업로드        │
                        └─────────────────────────────────┘

이번 실행 결과 (예시):
  data-preparation: abc1234 → 이미 존재 → SKIP
  train           : def5678 → 없음     → BUILD & PUSH
  evaluation      : abc1234 → 이미 존재 → SKIP

이후 pipeline.py 컴파일 시:
  ContainerSpec(image=…/data-preparation:abc1234)  ← 옛 이미지 재사용
  ContainerSpec(image=…/train           :def5678)  ← 새 이미지
  ContainerSpec(image=…/evaluation      :abc1234)  ← 옛 이미지 재사용
```

---

## ④ Vertex AI 콘솔에서 "실행 만들기" 누른 뒤 일어나는 일

```
┌─────────────────────────┐
│  사용자 (Vertex AI 콘솔) │
│                         │
│  파라미터 입력:          │
│   epochs=3              │
│   train_accelerator_    │
│     count=1 (T4 GPU)    │
└────────────┬────────────┘
             │ "제출"
             ▼
┌────────────────────────────────────────────────────────────────┐
│ Vertex AI Pipelines control plane                              │
│ aiplatform.googleapis.com/.../pipelineJobs                     │
│                                                                │
│  • template URI 로 AR (KFP) 에서 ci-cd-cifar10 (tag: latest)    │
│    YAML 가져옴                                                   │
│  • 파라미터 값 + 컴퓨팅 스펙으로 실행 그래프 인스턴스화            │
│  • run-id 생성, ML Metadata Context 레코드 생성                  │
│  • pipeline-root 아래 GCS 경로 미리 할당                         │
└────────────────────────────────────────────────────────────────┘
             │
             │   각 task 를 Custom Training Job 으로 디스패치
             │   (resource spec: cpu/mem/accel)
             ▼
┌────────────────────────────────────────────────────────────────┐
│ 워커 fleet (관리형 GKE/VM)                                       │
│                                                                │
│   ┌───────────────┐    ┌───────────┐    ┌────────────────┐     │
│   │ data-prep VM  │ ─> │ train VM  │ ─> │ evaluation VM  │     │
│   │ machine: e2-… │    │ + T4 GPU  │    │ machine: e2-…  │     │
│   │ image:        │    │ image:    │    │ image:         │     │
│   │   data-prep   │    │   train   │    │   evaluation   │     │
│   │   :abc1234    │    │   :def5678│    │   :abc1234     │     │
│   └───────┬───────┘    └─────┬─────┘    └───────┬────────┘     │
│           │ output_dataset    │ model            │ metrics      │
│           ▼                   ▼                  ▼              │
│        (GCS pipeline-root 의 고유 경로 — KFP 가 사전 할당)         │
└────────────────────────────────────────────────────────────────┘
             │
             │  태스크 종료마다 ML Metadata API 에 아티팩트 등록
             ▼
┌────────────────────────────────────────────────────────────────┐
│ Vertex ML Metadata                                             │
│  • Context  (run id)                                           │
│  • Execution per task                                          │
│  • Artifact: train_dataset, test_dataset, model, metrics       │
│      ↳ uri = gs://…/<run-id>/<task>/<output>/Dataset           │
│      ↳ metadata = {…} (사용자가 .metadata 에 넣은 것)            │
│      ↳ lineage edges: produced_by / consumed_by                │
└────────────────────────────────────────────────────────────────┘
             │
             ▼
       콘솔 UI 가 ML Metadata 와 Cloud Logging 을 쿼리해서
       실시간 그래프 / 아티팩트 카드 / 로그 탭을 그림
```

---

## ⑤ 워커 컨테이너 내부 — 한 task 실행 중 일어나는 모든 데이터 흐름

```
                            ┌─────────────────────────────────────────┐
                            │    Worker VM (Vertex AI managed)        │
                            │  ┌────────────────────────────────────┐ │
                            │  │ Container: train:def5678           │ │
                            │  │ (pytorch/pytorch:cuda12.1)         │ │
                            │  │                                    │ │
   train_dataset.path  ───> │  │  KFP launcher (PyPI: kfp)          │ │
   = /gcs/<bucket>/         │  │   ├─ env.IMAGE_REGISTRY            │ │
     <run-id>/              │  │   ├─ env.IMAGE_TAG                 │ │
     produce-data_*/        │  │   ├─ artifact uri ↔ path 변환      │ │
     train_dataset/Dataset  │  │   │  (`gs://…` → `/gcs/…`)          │ │
                            │  │   └─ user fn 호출                   │ │
                            │  │                                    │ │
                            │  │   user code: train/main.py         │ │
                            │  │   ├─ argparse:                     │ │
                            │  │   │    --train-input  /gcs/…       │ │
                            │  │   │    --model-output /gcs/…       │ │
                            │  │   ├─ torch.load(/gcs/…)            │ │
                            │  │   ├─ model = SimpleCNN().to(cuda)  │ │
                            │  │   ├─ for epoch: ...                │ │
                            │  │   │    print(f"…loss={…}")  ───────┼─┼──> stdout
                            │  │   └─ torch.save(state, /gcs/…)     │ │
                            │  │                                    │ │
                            │  │   KFP launcher (post-process):     │ │
                            │  │   └─ artifact .metadata dict       │ │
                            │  │      → JSON to /tmp/outputs/…      │ │
                            │  └────────────────┬───────────────────┘ │
                            │                   │                     │
                            │                   ▼                     │
                            │  ┌─────────────────────────────────┐    │
                            │  │ FUSE 드라이버 (커널)              │    │
                            │  └────────────┬────────────────────┘    │
                            │               │                         │
                            │               ▼                         │
                            │  ┌─────────────────────────────────┐    │
                            │  │ gcsfuse 데몬 (userspace)          │    │
                            │  │  • read: Range GET              │    │
                            │  │  • write: 로컬 buffer → close 시 │    │
                            │  │           Resumable upload      │    │
                            │  │  • stat: objects.get            │    │
                            │  └────────────┬────────────────────┘    │
                            │               │ HTTPS                   │
                            │               ▼                         │
                            │  ┌─────────────────────────────────┐    │
                            │  │ 노드 로깅 에이전트 (Fluent Bit)    │    │
                            │  │  /var/log/containers/*.log tail │    │
                            │  │  + resource labels 부착          │    │
                            │  └────────────┬────────────────────┘    │
                            └───────────────┼─────────────────────────┘
                                            │ HTTPS
              ┌─────────────────────────────┼─────────────────────────┐
              │                             │                         │
              ▼                             ▼                         ▼
   ┌────────────────────┐      ┌─────────────────────┐    ┌──────────────────┐
   │   GCS              │      │ Cloud Logging       │    │ Vertex ML        │
   │   pipeline-root    │      │ resource.type=      │    │ Metadata         │
   │   <bucket>/        │      │  PipelineJob        │    │  • Artifact 등록  │
   │   <run-id>/        │      │ labels:             │    │    (uri,metadata)│
   │   train_*/model/   │      │  pipeline_job_id    │    │  • Execution     │
   │   Model            │      │  task_name          │    │    edges         │
   └────────────────────┘      │  container_name     │    └──────────────────┘
                               └─────────────────────┘
                                       │
                                       ▼
                            (콘솔 "Logs" 탭이 동일 필터로
                             실시간 tail 쿼리)
```

---

## 다이어그램 간 매핑 — 콘솔에서 보이는 것이 어디서 오는지

| 콘솔 화면 | 백엔드 출처 | 다이어그램 |
|---|---|---|
| 파이프라인 → 템플릿 → 버전 목록 | AR (KFP repo) `test-registry` | ① 마지막 박스 |
| 실행 그래프 / 노드 박스 | Vertex ML Metadata (Context+Executions) | ④, ⑤ 우측 |
| 아티팩트 카드 (.uri, metadata) | Vertex ML Metadata (Artifact) | ⑤ 우측 |
| Logs 탭 | Cloud Logging (필터된 실시간 쿼리) | ⑤ 중앙 |
| 아티팩트의 실제 파일 | GCS pipeline-root | ⑤ 좌측 |

이 다섯 다이어그램이 합쳐지면 "내가 push 한 한 줄이 어떤 단계를 거쳐 콘솔의 한 그래프와 한 줄의 metric JSON 까지 도달하는가" 의 전체 그림이 됩니다.
