from pydantic import BaseModel, Field, HttpUrl


class ExtractRequest(BaseModel):
    url: HttpUrl = Field(examples=["https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=7068&MevzuatTur=1&MevzuatTertip=5"])


class ExtractResponse(BaseModel):
    url: str
    final_url: str
    title: str | None
    text: str
    char_count: int
    content_type: str
