"""Tests Katib"""

from functools import partial
from typing import NamedTuple

from kfp import components, dsl

func_to_container_op = partial(
    components.func_to_container_op,
    base_image='rocks.canonical.com:5000/kubeflow/examples/mnist-test:latest',
)


@func_to_container_op
def create_task(namespace: str, example: str) -> NamedTuple('Data', [('experiment_name', str)]):
    """"""

    from kubernetes import client, config
    from pprint import pprint
    import random
    import requests
    import string
    import yaml

    config.load_incluster_config()
    api = client.CustomObjectsApi()
    resource = yaml.safe_load(requests.get(example).text)
    resource['metadata']['name'] += '-' + ''.join(
        random.choice(string.ascii_lowercase) for _ in range(6)
    )
    resource['metadata']['namespace'] = 'admin'
    resource['spec']['maxTrialCount'] = 1
    resource['spec']['maxFailedTrialCount'] = 1
    resource['spec']['parallelTrialCount'] = 1

    pprint(resource)
    api.create_namespaced_custom_object(
        group="kubeflow.org",
        version="v1alpha3",
        namespace="admin",
        plural="experiments",
        body=resource,
    )

    return (resource['metadata']['name'],)


@func_to_container_op
def wait_task(namespace: str, experiment_name: str):
    """"""
    import requests
    import time
    import csv
    import json

    katib_ui = 'http://katib-ui.kubeflow.svc.cluster.local:8000/katib/fetch_hp_job_info/'

    for _ in range(240):
        response = requests.get(
            f'{katib_ui}?experimentName={experiment_name}&namespace={namespace}'
        )
        response.raise_for_status()
        trials = csv.DictReader(json.loads(response.text).splitlines())
        statuses = {t['trialName']: t['Status'] for t in trials}

        if statuses == {}:
            print("Waiting for jobs to be started.")
        elif set(statuses.values()) == {'Succeeded'}:
            print("All jobs completed successfully!")
            break
        else:
            print('Waiting for jobs to complete:')
            print(statuses)

        time.sleep(5)
    else:
        raise Exception("Waited too long for jobs to complete!")


@func_to_container_op
def delete_task(namespace: str, experiment_name: str):
    import requests

    katib_ui = 'http://katib-ui.kubeflow.svc.cluster.local:8000/katib/delete_experiment/'

    response = requests.get(f'{katib_ui}?experimentName={experiment_name}&namespace={namespace}')
    response.raise_for_status()


@dsl.pipeline(
    name='Katib Test', description='Tests Katib',
)
def katib_pipeline(
    namespace: str = 'admin',
    example: str = 'https://raw.githubusercontent.com/kubeflow/katib/master/examples/v1alpha3/grid-example.yaml',
):
    create = create_task(namespace, example)
    wait = wait_task(namespace, create.outputs['experiment_name'])
    _delete = delete_task(namespace, create.outputs['experiment_name']).after(wait)
