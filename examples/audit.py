import os
from pangea.config import PangeaConfig
from pangea.services import Audit

token = os.getenv("PANGEA_TOKEN")
config = PangeaConfig(base_domain="dev.pangea.cloud")
audit = Audit(token=token, config=config)

print("Log Data...")

data = {
    "action": "reboot",
    "actor": "villan",
    "target": "world",
    "status": "success",
}

log_response = audit.log(data)

print(f"Log Request ID: {log_response.request_id}, Result: {log_response.result}")

print("Search Data...")

search_res = audit.search(query="reboot", size=5)

if search_res.success:
    print("Search Request ID:", search_res.request_id, "\n")

    print(
        f"Results: {search_res.count} of {search_res.total} - next {search_res.next()}",
    )
    for row in search_res.result.audits:
        print(f"{row.created}\t{row.actor}\t{row.action}\t{row.target}\t{row.status}")

    # get the next page
    if search_res.next():
        search_res = audit.search(**search_res.next())
        print("Search Next", search_res.results)
else:
    print("Search Failed:", search_res.code, search_res.status)
