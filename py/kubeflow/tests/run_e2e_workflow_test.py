import os
import unittest
import mock
from kubeflow.testing import run_e2e_workflow
import six
import tempfile
import yaml


class TestRunE2eWorkflow(unittest.TestCase):

  def assertItemsMatchRegex(self, expected, actual):
    """Check that expected matches actual.

    Args:
      Expected: List of strings. These can be regex.
      Actual: Actual items.
    """
    self.assertEqual(len(expected), len(actual))
    for index, e in enumerate(expected):
      # assertRegexpMatches uses re.search so we automatically append
      # ^ and $ so we match the beginning and end of the string.
      pattern = "^" + e + "$"
      six.assertRegex(self, actual[index], pattern)

  @mock.patch("kubeflow.testing.run_e2e_workflow.prow_artifacts"
              ".finalize_prow_job")
  @mock.patch("kubeflow.testing.run_e2e_workflow.util"
              ".maybe_activate_service_account")
  @mock.patch("kubeflow.testing.run_e2e_workflow.util.upload_file_to_gcs")
  @mock.patch("kubeflow.testing.run_e2e_workflow.util.upload_to_gcs")
  @mock.patch("kubeflow.testing.run_e2e_workflow.util.load_kube_config")
  @mock.patch("kubeflow.testing.run_e2e_workflow.argo_client.wait_for_workflows")
  @mock.patch("kubeflow.testing.run_e2e_workflow.util.configure_kubectl")
  @mock.patch("kubeflow.testing.run_e2e_workflow.util.run")
  def testWithConfig(self, mock_run, mock_configure, mock_wait_for_workflows,
                     *unused_mocks):  # pylint: disable=no-self-use,unused-argument
    """Test creating a workflow from a config file."""
    # We need to set cwd and the app_dir in the config file consistently.
    # The app_dir will be relative to the working dir.
    # We set cwd to the root of the repo and then app dir relative to that.
    this_dir = os.path.basename(__file__)
    cwd = os.path.abspath(os.path.join(this_dir, "..", "..", "..", ".."))
    # Current directory is in the format:
    # "/mnt/test-data-volume/kubeflow-testing-12345/src/kubeflow/testing"
    # We need to parse the actual repo root here.
    repo_dir = cwd
    config = {
      "workflows": [
        {"app_dir": "workflows",
         "component": "workflows",
         "name": "wf",
         "params": {
           "param1": "valuea",
           "param2": 10,
         },
        },]
    }
    with tempfile.NamedTemporaryFile(delete=False) as hf:
      yaml.dump(config, hf)
      name = hf.name
    os.environ = {"REPO_OWNER": "fake_org",
                  "REPO_NAME": "fake_name",
                  "PULL_NUMBER": "77",
                  "PULL_PULL_SHA": "123abc",
                  "JOB_NAME": "kubeflow-presubmit",
                  "JOB_TYPE": "presubmit",
                  "BUILD_NUMBER": "1234",
                  "BUILD_ID": "11",
                  "PULL_BASE_REF": "test_branch"}

    mock_run.return_value = "ab1234"

    args = ["--project=some-project", "--cluster=some-cluster",
            "--zone=us-east1-d", "--bucket=some-bucket",
            "--config_file=" + name,
            "--repos_dir=" + repo_dir]
    mock_wait_for_workflows.return_value = []
    run_e2e_workflow.main(args)

    mock_configure.assert_called_once_with("some-project", "us-east1-d",
                                           "some-cluster",)

    expected_calls = [
      ["git", "fetch", "origin", "test_branch:refs/remotes/origin/test_branch"],
      ["git", "merge-base", "HEAD", "remotes/origin/test_branch"],
      ["git", "diff", "--name-only", "ab1234"],
      ["ks-13", "version"],
      ["ks-13", "env", "add", "kubeflow-presubmit-wf-77-123abc-1234-.*",
       "--namespace=kubeflow-test-infra"],
      ["ks-13", "param", "set", "--env=.*", "workflows", "name",
           "kubeflow-presubmit-wf-77-123abc-1234-[0-9a-z]{4}"],
      ["ks-13", "param", "set",
           "--env=.*",
           "workflows", "prow_env",
           "BUILD_ID=11,BUILD_NUMBER=1234,JOB_NAME=kubeflow-presubmit,"
           "JOB_TYPE=presubmit,PULL_NUMBER=77,PULL_PULL_SHA=123abc,"
           "REPO_NAME=fake_name,REPO_OWNER=fake_org"],
      ["ks-13", "param", "set",
           "--env=.*",
           "workflows", "namespace",
           "kubeflow-test-infra"],
      ["ks-13", "param", "set",
           "--env=.*",
           "workflows", "bucket", "some-bucket"],
      ["ks-13", "param", "set",
           "--env=.*",
           "workflows", "param1", "valuea"],
      ["ks-13", "param", "set",
           "--env=.*",
           "workflows", "param2", "10"],
      ["ks-13", "show", "kubeflow-presubmit.*", "-c", "workflows"],
      ["ks-13", "apply", "kubeflow-presubmit.*", "-c", "workflows"],
    ]

    for i, expected in enumerate(expected_calls):
      self.assertItemsMatchRegex(
        expected,
        mock_run.call_args_list[i][0][0])
      if mock_run.call_args_list[i][0][0][0] == 'git':
        self.assertEqual(
          os.path.join(cwd, os.environ['REPO_OWNER'], os.environ['REPO_NAME']),
          mock_run.call_args_list[i][1]['cwd'])
      elif 'cwd' in mock_run.call_args_list[i][1]:
        self.assertEqual(
          os.path.join(cwd, 'workflows'),
          mock_run.call_args_list[i][1]["cwd"])

if __name__ == "__main__":
  unittest.main()
