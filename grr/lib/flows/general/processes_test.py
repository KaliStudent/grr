#!/usr/bin/env python
"""Test the process list module."""

import os

from grr.lib import action_mocks
from grr.lib import flags
from grr.lib import flow
from grr.lib.flows.general import processes as flow_processes
from grr.lib.rdfvalues import client as rdf_client
from grr.test_lib import flow_test_lib
from grr.test_lib import test_lib


class ListProcessesMock(action_mocks.FileFinderClientMock):
  """Client with real file actions and mocked-out ListProcesses."""

  def __init__(self, processes_list):
    super(ListProcessesMock, self).__init__()
    self.processes_list = processes_list

  def ListProcesses(self, _):
    return self.processes_list


class ListProcessesTest(flow_test_lib.FlowTestsBaseclass):
  """Test the process listing flow."""

  def testProcessListingOnly(self):
    """Test that the ListProcesses flow works."""

    client_mock = ListProcessesMock([
        rdf_client.Process(
            pid=2,
            ppid=1,
            cmdline=["cmd.exe"],
            exe="c:\\windows\\cmd.exe",
            ctime=long(1333718907.167083 * 1e6))
    ])

    flow_urn = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=flow_processes.ListProcesses.__name__,
        token=self.token)
    for s in flow_test_lib.TestFlowHelper(
        flow_urn, client_mock, client_id=self.client_id, token=self.token):
      session_id = s

    # Check the output collection
    processes = flow.GRRFlow.ResultCollectionForFID(
        session_id, token=self.token)

    self.assertEqual(len(processes), 1)
    self.assertEqual(processes[0].ctime, 1333718907167083L)
    self.assertEqual(processes[0].cmdline, ["cmd.exe"])

  def testProcessListingWithFilter(self):
    """Test that the ListProcesses flow works with filter."""

    client_mock = ListProcessesMock([
        rdf_client.Process(
            pid=2,
            ppid=1,
            cmdline=["cmd.exe"],
            exe="c:\\windows\\cmd.exe",
            ctime=long(1333718907.167083 * 1e6)),
        rdf_client.Process(
            pid=3,
            ppid=1,
            cmdline=["cmd2.exe"],
            exe="c:\\windows\\cmd2.exe",
            ctime=long(1333718907.167083 * 1e6)),
        rdf_client.Process(
            pid=4,
            ppid=1,
            cmdline=["missing_exe.exe"],
            ctime=long(1333718907.167083 * 1e6)),
        rdf_client.Process(
            pid=5,
            ppid=1,
            cmdline=["missing2_exe.exe"],
            ctime=long(1333718907.167083 * 1e6))
    ])

    flow_urn = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=flow_processes.ListProcesses.__name__,
        filename_regex=r".*cmd2.exe",
        token=self.token)
    for s in flow_test_lib.TestFlowHelper(
        flow_urn, client_mock, client_id=self.client_id, token=self.token):
      session_id = s

    # Expect one result that matches regex
    processes = flow.GRRFlow.ResultCollectionForFID(
        session_id, token=self.token)

    self.assertEqual(len(processes), 1)
    self.assertEqual(processes[0].ctime, 1333718907167083L)
    self.assertEqual(processes[0].cmdline, ["cmd2.exe"])

    # Expect two skipped results
    logs = flow.GRRFlow.LogCollectionForFID(flow_urn, token=self.token)
    for log in logs:
      if "Skipped 2" in log.log_message:
        return
    raise RuntimeError("Skipped process not mentioned in logs")

  def testProcessListingFilterConnectionState(self):
    p1 = rdf_client.Process(
        pid=2,
        ppid=1,
        cmdline=["cmd.exe"],
        exe="c:\\windows\\cmd.exe",
        ctime=long(1333718907.167083 * 1e6),
        connections=rdf_client.NetworkConnection(family="INET", state="CLOSED"))
    p2 = rdf_client.Process(
        pid=3,
        ppid=1,
        cmdline=["cmd2.exe"],
        exe="c:\\windows\\cmd2.exe",
        ctime=long(1333718907.167083 * 1e6),
        connections=rdf_client.NetworkConnection(family="INET", state="LISTEN"))
    p3 = rdf_client.Process(
        pid=4,
        ppid=1,
        cmdline=["missing_exe.exe"],
        ctime=long(1333718907.167083 * 1e6),
        connections=rdf_client.NetworkConnection(
            family="INET", state="ESTABLISHED"))
    client_mock = ListProcessesMock([p1, p2, p3])

    flow_urn = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=flow_processes.ListProcesses.__name__,
        connection_states=["ESTABLISHED", "LISTEN"],
        token=self.token)
    for s in flow_test_lib.TestFlowHelper(
        flow_urn, client_mock, client_id=self.client_id, token=self.token):
      session_id = s

    processes = flow.GRRFlow.ResultCollectionForFID(
        session_id, token=self.token)
    self.assertEqual(len(processes), 2)
    states = set()
    for process in processes:
      states.add(str(process.connections[0].state))
    self.assertItemsEqual(states, ["ESTABLISHED", "LISTEN"])

  def testWhenFetchingFiltersOutProcessesWithoutExeAndConnectionState(self):
    p1 = rdf_client.Process(
        pid=2,
        ppid=1,
        cmdline=["test_img.dd"],
        ctime=long(1333718907.167083 * 1e6))

    p2 = rdf_client.Process(
        pid=2,
        ppid=1,
        cmdline=["cmd.exe"],
        exe="c:\\windows\\cmd.exe",
        ctime=long(1333718907.167083 * 1e6),
        connections=rdf_client.NetworkConnection(
            family="INET", state="ESTABLISHED"))

    client_mock = ListProcessesMock([p1, p2])

    for s in flow_test_lib.TestFlowHelper(
        flow_processes.ListProcesses.__name__,
        client_mock,
        fetch_binaries=True,
        client_id=self.client_id,
        connection_states=["LISTEN"],
        token=self.token):
      session_id = s

    # No output matched.
    processes = flow.GRRFlow.ResultCollectionForFID(
        session_id, token=self.token)
    self.assertEqual(len(processes), 0)

  def testFetchesAndStoresBinary(self):
    process = rdf_client.Process(
        pid=2,
        ppid=1,
        cmdline=["test_img.dd"],
        exe=os.path.join(self.base_path, "test_img.dd"),
        ctime=long(1333718907.167083 * 1e6))

    client_mock = ListProcessesMock([process])

    for s in flow_test_lib.TestFlowHelper(
        flow_processes.ListProcesses.__name__,
        client_mock,
        client_id=self.client_id,
        fetch_binaries=True,
        token=self.token):
      session_id = s

    results = flow.GRRFlow.ResultCollectionForFID(session_id, token=self.token)
    binaries = list(results)
    self.assertEqual(len(binaries), 1)
    self.assertEqual(binaries[0].pathspec.path, process.exe)
    self.assertEqual(binaries[0].st_size, os.stat(process.exe).st_size)

  def testDoesNotFetchDuplicates(self):
    process1 = rdf_client.Process(
        pid=2,
        ppid=1,
        cmdline=["test_img.dd"],
        exe=os.path.join(self.base_path, "test_img.dd"),
        ctime=long(1333718907.167083 * 1e6))

    process2 = rdf_client.Process(
        pid=3,
        ppid=1,
        cmdline=["test_img.dd", "--arg"],
        exe=os.path.join(self.base_path, "test_img.dd"),
        ctime=long(1333718907.167083 * 1e6))

    client_mock = ListProcessesMock([process1, process2])

    for s in flow_test_lib.TestFlowHelper(
        flow_processes.ListProcesses.__name__,
        client_mock,
        client_id=self.client_id,
        fetch_binaries=True,
        token=self.token):
      session_id = s

    processes = flow.GRRFlow.ResultCollectionForFID(
        session_id, token=self.token)
    self.assertEqual(len(processes), 1)

  def testWhenFetchingIgnoresMissingFiles(self):
    process1 = rdf_client.Process(
        pid=2,
        ppid=1,
        cmdline=["test_img.dd"],
        exe=os.path.join(self.base_path, "test_img.dd"),
        ctime=long(1333718907.167083 * 1e6))

    process2 = rdf_client.Process(
        pid=2,
        ppid=1,
        cmdline=["file_that_does_not_exist"],
        exe=os.path.join(self.base_path, "file_that_does_not_exist"),
        ctime=long(1333718907.167083 * 1e6))

    client_mock = ListProcessesMock([process1, process2])

    for s in flow_test_lib.TestFlowHelper(
        flow_processes.ListProcesses.__name__,
        client_mock,
        client_id=self.client_id,
        fetch_binaries=True,
        token=self.token,
        check_flow_errors=False):
      session_id = s

    results = flow.GRRFlow.ResultCollectionForFID(session_id, token=self.token)
    binaries = list(results)
    self.assertEqual(len(binaries), 1)
    self.assertEqual(binaries[0].pathspec.path, process1.exe)


def main(argv):
  # Run the full test suite
  test_lib.main(argv)


if __name__ == "__main__":
  flags.StartMain(main)
