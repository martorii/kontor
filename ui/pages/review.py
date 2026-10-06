import streamlit as st

from api_client import ApiClient, ApiError, ApiUnreachableError
from report_common import money
from transaction_table import assignable_categories

api = ApiClient.from_env()
PAGE_SIZE = 25

st.title("Review")
assignable = assignable_categories(api)


def show_rerun() -> None:
    st.caption(
        "Applies the current rules to every transaction that was not categorized by hand. "
        "Preview first: a dry run changes nothing."
    )
    if st.button("Preview rerun"):
        try:
            st.session_state["rerun_preview"] = api.rerun_rules(dry_run=True)
        except (ApiError, ApiUnreachableError) as exc:
            st.session_state.pop("rerun_preview", None)
            st.error(str(exc))
    preview = st.session_state.get("rerun_preview")
    if preview is None:
        return
    st.write(
        f"{preview['evaluated']} evaluated · {preview['changed']} would change · "
        f"{preview['unchanged']} unchanged"
    )
    if preview["changes"]:
        st.dataframe(
            [
                {
                    "Transaction": c["transaction_id"],
                    "From": assignable.get(c["old_category"], c["old_category"] or "–"),
                    "To": assignable.get(c["new_category"], c["new_category"] or "–"),
                    "Rule": c["rule_id"] or "–",
                }
                for c in preview["changes"]
            ],
            hide_index=True,
            use_container_width=True,
        )
    if st.button("Apply rerun", type="primary", disabled=preview["changed"] == 0):
        try:
            result = api.rerun_rules(dry_run=False)
        except (ApiError, ApiUnreachableError) as exc:
            st.error(str(exc))
            return
        st.session_state.pop("rerun_preview", None)
        st.session_state["rerun_done"] = result["changed"]
        st.rerun()


if "rerun_done" in st.session_state:
    st.success(f"Rerun applied: {st.session_state.pop('rerun_done')} transactions changed.")

with st.expander("Re-run rules"):
    show_rerun()

try:
    total_pages = 1
    first = api.uncategorized(PAGE_SIZE, 0)
    total_pages = max(1, -(-first["total"] // PAGE_SIZE))
    page_number = int(
        st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
        if total_pages > 1
        else 1
    )
    page = (
        first if page_number == 1 else api.uncategorized(PAGE_SIZE, (page_number - 1) * PAGE_SIZE)
    )
except (ApiError, ApiUnreachableError) as exc:
    st.error(str(exc))
    st.stop()

if page["total"] == 0:
    st.success("Nothing to review: every transaction is categorized.")
    st.stop()

st.subheader(f"{page['total']} uncategorized")


def assign(transaction_id: int, category: str) -> None:
    try:
        api.set_category(transaction_id, category)
    except (ApiError, ApiUnreachableError) as exc:
        st.error(str(exc))
    else:
        st.rerun()


for t in page["items"]:
    with st.container(border=True):
        top, amount = st.columns([4, 1])
        top.markdown(f"**{t['counterparty']}** · {t['booking_date']}")
        top.caption(t["purpose"] or "–")
        amount.markdown(f"**{money(t['amount'], t['currency'])}**")

        suggested = next((s for s in t["suggestions"] if s["category"] in assignable), None)
        accept, pick, save = st.columns([2, 3, 1], vertical_alignment="bottom")
        if suggested is not None:
            confidence = suggested["confidence"]
            hint = f" ({confidence:.0%})" if confidence is not None else ""
            if accept.button(
                f"Accept {assignable[suggested['category']]}{hint}",
                key=f"accept-{t['id']}",
                type="primary",
            ):
                assign(t["id"], suggested["category"])
        else:
            accept.caption("No suggestion")
        target = pick.selectbox(
            "Category",
            list(assignable),
            index=None,
            format_func=lambda slug: assignable[slug],
            placeholder="Choose a category",
            key=f"pick-{t['id']}",
            label_visibility="collapsed",
        )
        if save.button("Save", key=f"save-{t['id']}", disabled=target is None):
            assign(t["id"], str(target))
