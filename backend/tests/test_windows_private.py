"""Private storage on Windows: what the descriptor check accepts and refuses."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows private storage requires Windows")


def test_the_built_in_administrator_is_written_as_its_alias_and_its_own_storage_is_accepted():
    from tracker.platform.windows_private import account_sid, descriptor_problem, sddl_name

    domain = account_sid().rsplit("-", 1)[0]
    administrator = sddl_name(f"{domain}-500")
    assert administrator == "LA", "descriptor strings name the built-in Administrator LA"
    own = f"O:{administrator}D:PAI(A;OICI;FA;;;{administrator})(A;OICI;FA;;;SY)"
    assert descriptor_problem(own, administrator) is None
    assert descriptor_problem(own, f"{domain}-500") is not None, "the full SID never appears in such a descriptor"


def test_an_ordinary_account_keeps_its_full_sid():
    from tracker.platform.windows_private import account_sid, sddl_name

    domain = account_sid().rsplit("-", 1)[0]
    assert sddl_name(f"{domain}-1001") == f"{domain}-1001"


def test_a_descriptor_owned_or_shared_elsewhere_is_refused():
    from tracker.platform.windows_private import descriptor_problem

    me = "S-1-5-21-1-2-3-1001"
    safe = f"O:{me}D:P(A;OICI;FA;;;{me})(A;OICI;FA;;;SY)"
    assert descriptor_problem(safe, me) is None
    assert "unsafe owner" in descriptor_problem(f"O:BAD:P(A;OICI;FA;;;{me})", me)
    assert "unsafe owner" in descriptor_problem(f"O:{me}D:NO_ACCESS_CONTROL", me)
    assert "unsafe owner" in descriptor_problem(f"O:{me}D:P", me), "no entries at all"
    assert "another account" in descriptor_problem(f"O:{me}D:P(A;OICI;FA;;;{me})(A;OICI;FR;;;BU)", me)
    assert "another account" in descriptor_problem(f"O:{me}D:P(D;OICI;FA;;;WD)(A;OICI;FA;;;{me})", me), \
        "a deny entry is still an entry this check does not expect"


def test_an_elevated_process_accepts_the_administrators_owner_it_gives_its_own_files():
    from tracker.platform.windows_private import descriptor_problem

    me = "S-1-5-21-1-2-3-1001"
    by_administrators = f"O:BAD:PAI(A;OICI;FA;;;{me})(A;OICI;FA;;;SY)"
    assert descriptor_problem(by_administrators, me, "BA") is None, "elevated: files this process makes are BA's"
    assert "unsafe owner" in descriptor_problem(by_administrators, me, me), "not elevated: BA is someone else"
    assert "unsafe owner" in descriptor_problem(by_administrators, me), "without a default owner, only the account"
    assert "another account" in descriptor_problem(f"O:BAD:PAI(A;OICI;FA;;;{me})(A;OICI;FA;;;BA)", me, "BA"), \
        "owning is not the same as being allowed in: no entry for the Administrators group"


def test_this_process_names_its_default_owner():
    from tracker.platform.windows_private import account_sid, default_owner_sid, sddl_name

    assert sddl_name(default_owner_sid()) in {sddl_name(account_sid()), "BA"}


def test_a_new_private_directory_passes_its_own_check(tmp_path):
    from tracker.platform.windows_private import private_directory, require_private

    private_directory(tmp_path / "private")
    require_private(tmp_path / "private")
