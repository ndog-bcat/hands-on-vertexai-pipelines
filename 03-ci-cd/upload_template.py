"""컴파일된 KFP 파이프라인 YAML 을 Artifact Registry KFP repo 에 업로드한다.

Vertex AI 콘솔의 "파이프라인 → 템플릿" 화면에서 등록된 템플릿이 보이고,
거기서 "실행 만들기" 로 원하는 시점에 실행할 수 있게 된다.

환경변수:
    KFP_HOST       — 예) https://us-kfp.pkg.dev/<project>/<repo>
    TEMPLATE_PATH  — 예) 03-ci-cd/ci-cd-pipeline.yaml
    TAGS           — 콤마 구분, 예) "abc1234,latest"

인증은 Application Default Credentials (ADC) 를 사용한다.
GitHub Actions 에서는 google-github-actions/auth 가 이미 ADC 를 깔아 둠.
"""

import os
import sys

from kfp.registry import RegistryClient


def main() -> None:
    host = os.environ["KFP_HOST"]
    template = os.environ["TEMPLATE_PATH"]
    tags_csv = os.environ.get("TAGS", "latest")
    tags = [t.strip() for t in tags_csv.split(",") if t.strip()]

    print(f"Uploading {template} to {host} with tags={tags}")

    client = RegistryClient(host=host)
    result = client.upload_pipeline(file_name=template, tags=tags)

    print(f"Upload complete: {result}", file=sys.stdout)


if __name__ == "__main__":
    main()
