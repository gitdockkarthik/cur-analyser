# Phase 2 — S3 integration placeholder


class S3Client:
    """S3 client for Phase 2 — reading CUR files directly from S3."""

    def __init__(
        self,
        bucket: str,
        prefix: str,
        region: str,
        access_key: str,
        secret_key: str,
    ):
        raise NotImplementedError("S3 integration is Phase 2 — not yet implemented")

    def test_connection(self) -> bool:
        raise NotImplementedError("Phase 2")

    def list_cur_files(self):
        raise NotImplementedError("Phase 2")

    def download_file(self, s3_key: str, local_path: str):
        raise NotImplementedError("Phase 2")
