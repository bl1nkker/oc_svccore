from urllib.parse import parse_qsl, quote, urlencode

from pydantic import BaseModel

from oc_svccore.config import getter


class DbConfig(BaseModel):
    url: str
    user: str
    password: str

    def postgres_url(self) -> str:
        address, _, query = self.url.partition("?")
        params = dict(parse_qsl(query))
        # PostgreSQL rejects search_path as a url parameter, it only takes it through options.
        if search_path := params.pop("search_path", None):
            params["options"] = f"-csearch_path={search_path}"
        url = f"postgresql://{quote(self.user, safe='')}:{quote(self.password, safe='')}@{address}"
        return f"{url}?{urlencode(params)}" if params else url


get_db_config = getter(
    DbConfig,
    lambda get: dict(url=get("PSQL__URL"), user=get("PSQL__USER"), password=get("PSQL__PASSWORD")),
)
