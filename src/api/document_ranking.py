from flask import Blueprint, request
from src.document_ranking.tf_idf import TfIdf
import json

bp_document_ranking = Blueprint(
    "document_ranking",
    __name__,
)


@bp_document_ranking.route("/tf_idf")
def get_tf_idf_ranks():
    try:
        keyword = request.args.get("keyword", default="", type=str)

        tf_idf = TfIdf()
        if keyword == "":
            response = {
                "ok": False,
                "message": "Keyword tidak ada. Masukkan keyword pada url seperti '?keyword=barcelona'",
            }
        else:
            print("siniiii")
            data = tf_idf.get_all_tfidf_for_api(keyword)
            print(data)
            response = {
                "ok": True,
                "message": "Sukses",
                "data": data,
            }
        json_obj = json.dumps(response, indent=4, default=str)
        return json.loads(json_obj), 200

    except Exception as e:
        return {
            "ok": False,
            "message": e,
        }, 500
