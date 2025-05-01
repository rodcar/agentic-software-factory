from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.mgmt.containerinstance import ContainerInstanceManagementClient
from azure.mgmt.containerinstance.models import (
    ContainerGroup,
    Container,
    ContainerGroupRestartPolicy,
    EnvironmentVariable,
    ResourceRequests,
    ResourceRequirements,
    OperatingSystemTypes,
    ImageRegistryCredential,
)
import time
import logging


def create_container(
    subscription_id,
    resource_group,
    container_group_name,
    container_image,
    registry_server,
    registry_username,
    registry_password,
    environment_variables,
    tenant_id=None,
    client_id=None,
    client_secret=None,
    location="westeurope",
    memory_in_gb=4.0,
    cpu=1.0,
    os_type=OperatingSystemTypes.LINUX,
    restart_policy=ContainerGroupRestartPolicy.NEVER
):
    """
    Create an Azure Container Instance with the specified parameters.
    
    Args:
        subscription_id (str): Azure subscription ID
        resource_group (str): Azure resource group name
        container_group_name (str): Name for the container group
        container_image (str): Container image to deploy
        registry_server (str): Container registry server address
        registry_username (str): Container registry username
        registry_password (str): Container registry password
        environment_variables (dict): Dictionary of environment variables {name: value}
        tenant_id (str, optional): Azure tenant ID for service principal auth
        client_id (str, optional): Azure client ID for service principal auth
        client_secret (str, optional): Azure client secret for service principal auth
        location (str, optional): Azure region. Defaults to "westeurope".
        memory_in_gb (float, optional): Memory allocation in GB. Defaults to 4.0.
        cpu (float, optional): CPU allocation. Defaults to 1.0.
        os_type (OperatingSystemTypes, optional): Container OS type. Defaults to LINUX.
        restart_policy (ContainerGroupRestartPolicy, optional): Restart policy. Defaults to NEVER.
    
    Returns:
        The created container group
    """
    # Convert environment variables dictionary to list of EnvironmentVariable objects
    env_vars = [
        EnvironmentVariable(name=name, value=value)
        for name, value in environment_variables.items()
    ]

    # Set up resource requirements
    resource_requests = ResourceRequests(memory_in_gb=memory_in_gb, cpu=cpu)
    resource_requirements = ResourceRequirements(requests=resource_requests)

    # Set up container definition
    container = Container(
        name=container_group_name,
        image=container_image,
        resources=resource_requirements,
        environment_variables=env_vars
    )

    # Set up container group
    container_group = ContainerGroup(
        location=location,
        containers=[container],
        os_type=os_type,
        restart_policy=restart_policy,
        image_registry_credentials=[
            ImageRegistryCredential(
                server=registry_server,
                username=registry_username,
                password=registry_password
            )
        ]
    )

    # Authenticate using service principal if credentials are provided, otherwise fall back to DefaultAzureCredential
    if tenant_id and client_id and client_secret:
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
    else:
        credential = DefaultAzureCredential()
    
    client = ContainerInstanceManagementClient(credential, subscription_id)

    # Create the container group
    poller = client.container_groups.begin_create_or_update(resource_group, container_group_name, container_group)
    result = poller.result()
    
    print(f"Container group '{result.name}' is running.")
    return result


def wait_for_container_termination(
    subscription_id,
    resource_group,
    container_group_name,
    tenant_id=None,
    client_id=None,
    client_secret=None,
    timeout_seconds=3600,  # Default timeout of 1 hour
    check_interval_seconds=30  # Check every 30 seconds
):
    """
    Wait for a container group to reach "Terminated" state.
    
    Args:
        subscription_id (str): Azure subscription ID
        resource_group (str): Azure resource group name
        container_group_name (str): Name of the container group to monitor
        tenant_id (str, optional): Azure tenant ID for service principal auth
        client_id (str, optional): Azure client ID for service principal auth
        client_secret (str, optional): Azure client secret for service principal auth
        timeout_seconds (int, optional): Maximum time to wait in seconds. Defaults to 3600 (1 hour).
        check_interval_seconds (int, optional): Time between status checks in seconds. Defaults to 30.
    
    Returns:
        dict: Container group details including final state, or None if timeout reached
    """
    # Authenticate using service principal if credentials are provided, otherwise fall back to DefaultAzureCredential
    if tenant_id and client_id and client_secret:
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
    else:
        credential = DefaultAzureCredential()
    
    client = ContainerInstanceManagementClient(credential, subscription_id)
    
    start_time = time.time()
    elapsed_time = 0
    
    logging.info(f"Waiting for container group '{container_group_name}' to terminate...")
    
    while elapsed_time < timeout_seconds:
        container_group = client.container_groups.get(resource_group, container_group_name)
        
        # Get the first container's state
        instance_view = container_group.containers[0].instance_view
        
        # Check if instance view exists and has current_state
        if instance_view and hasattr(instance_view, 'current_state'):
            current_state = instance_view.current_state.state
            logging.info(f"Container '{container_group_name}' current state: {current_state}")
            
            # Check if the container is terminated
            if current_state == "Terminated":
                logging.info(f"Container '{container_group_name}' has terminated after {elapsed_time} seconds")
                return container_group
        
        # Wait before checking again
        time.sleep(check_interval_seconds)
        elapsed_time = time.time() - start_time
    
    logging.warning(f"Timeout reached waiting for container '{container_group_name}' to terminate")
    return None