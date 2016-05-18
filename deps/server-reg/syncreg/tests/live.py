
import sys
import json
import random
import optparse

import services.user
from services.http_helpers import get_url
from services.respcodes import WEAVE_INVALID_CAPTCHA


def assertEquals(lhs, rhs):
    assert lhs == rhs, "ERROR: %s != %s" % (lhs, rhs)


def assertOneOf(item, items):
    assert item in items, "ERROR: %s not in %s" % (item, items)


def main(argv):
    usage = "Usage: %prog [options] <reg-server-url> [<node-server-url>]"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option("-u", "--username",
                      help="username to use for test account")
    parser.add_option("-p", "--password",
                      help="password to use for test account")

    try:
        opts, args = parser.parse_args(argv)
    except SystemExit, e:
        return e.args[0]
    if len(args) < 2 or len(args) > 3:
        parser.print_usage()
        return 2

    if opts.username is None:
        opts.username = "user%d@mockmyid.com" % (random.randint(1, 1000000),)
    if opts.password is None:
        opts.password = "iamabadpassword"

    username = services.user.extract_username(opts.username)
    creds = {"user": username, "password": opts.password}

    reg_url = args[1].rstrip("/") + "/user/1.0"
    print "TESTING USER API AT", reg_url
    if len(args) == 2:
        node_name = "weave"
        node_url = reg_url
    else:
        node_name = "sync"
        node_url = args[2].rstrip("/") + "/1.0"
        print "TESTING NODE API AT", node_url

    reg_url = reg_url + "/" + username
    node_url = node_url + "/" + username + "/node/" + node_name

    # Delete the account if it already exists.
    print "CHECKING PRE-EXISTING ACCOUNT"
    status, headers, body = get_url(reg_url)
    assertEquals(status, 200)
    assertOneOf(body, ("1", "0"))
    if body == "1":
        print "DELETING PRE-EXISTING ACCOUNT"
        status, headers, body = get_url(reg_url, "DELETE", **creds)
        assertEquals(status, 200)

    # Create the account.
    print "CREATING THE ACCOUNT"
    user_data = {
        "email": opts.username,
        "password": opts.password,
    }
    status, headers, body = get_url(reg_url, "PUT", json.dumps(user_data))
    if status == 400:
        if int(body) == WEAVE_INVALID_CAPTCHA:
            assert False, "cannot test server with captchas enabled"
    assertEquals(status, 200)

    # Get a new node assignment.
    print "GETTING NODE ASSIGNMENT"
    status, headers, node1 = get_url(node_url)
    assertEquals(status, 200)
    print"NODE IS:", node1

    # Check that node assignment is consistent.
    print "GETTING NODE ASSIGNMENT AGAIN"
    status, headers, node2 = get_url(node_url)
    assertEquals(status, 200)
    print"NODE IS:", node2
    assertEquals(node1, node2)

    # Clean up the account.
    print "DELETING THE ACCOUNT"
    status, headers, body = get_url(reg_url, "DELETE", **creds)
    assertEquals(status, 200)

    # That'll do it.
    print "OK!"
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
