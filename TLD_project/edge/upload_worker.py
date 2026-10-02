# -*- coding: utf-8 -*-
"""持久化病害原图 HTTP 补传线程。"""

import os
import threading
import time


class ImageUploadWorker(object):
    def __init__(self, store, http_client, logger):
        self.store = store
        self.http = http_client
        self.logger = logger
        self._running = False
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="ImageUpload", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join()
        self._thread = None

    def _loop(self):
        while self._running:
            rows = self.store.due_images(2)
            if not rows:
                time.sleep(0.5)
                continue
            for row in rows:
                if not self._running:
                    break
                try:
                    if row["attempts"]:
                        self.logger.info("[IMAGE_RETRY] image_id={}".format(row["image_id"]))
                    self.http.upload_image(
                        row["image_id"], row["inspection_id"], row["data_id"],
                        row["captured_at"], row["path"]
                    )
                    # 顺序不可改变：云端明确成功 -> SQLite 提交完成 -> 删除临时文件。
                    self.store.mark_image_done(row["id"])
                    try:
                        if os.path.isfile(row["path"]):
                            os.remove(row["path"])
                    except OSError as exc:
                        self.logger.warning("已上传图片的临时文件稍后清理: {}".format(type(exc).__name__))
                    self.logger.info("[IMAGE_HTTP_SUCCESS] image_id={}（业务确认已提交 SQLite）".format(row["image_id"]))
                except Exception as exc:
                    self.store.fail_image(row["id"], type(exc).__name__)
                    self.logger.warning("[IMAGE_RETRY_FAILED] image_id={}".format(row["image_id"]))
                    time.sleep(0.2)
