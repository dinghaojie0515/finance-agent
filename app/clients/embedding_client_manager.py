import asyncio
from typing import Optional

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.conf.app_config import EmbeddingConfig, app_config


class EmbeddingClientManager:
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.client: Optional[HuggingFaceEndpointEmbeddings] = None

    def _get_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    def init(self) -> None:
        # 自托管 TEI 服务：将 http://host:port 作为 model 传入 InferenceClient
        self.client = HuggingFaceEndpointEmbeddings(model=self._get_url())


embedding_client_manager = EmbeddingClientManager(app_config.embedding)

if __name__ == '__main__':
    embedding_client_manager.init()

    embedding = embedding_client_manager.client

    async def test():
        text = "what is deep learning"
        result = embedding.embed_query(text)
        # print(type(result))
        # print(result)
        # print(len(result))

        # await embedding.aembed_documents([text])
        print(result)


    asyncio.run(test())