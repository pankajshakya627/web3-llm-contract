pragma solidity ^0.8.13;

import '@openzeppelin/contracts/token/ERC20/ERC20.sol';
import '@openzeppelin/contracts/access/AccessControl.sol';

contract MyToken is ERC20, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256('MINTER_ROLE');

    constructor(address admin) ERC20('MyToken', 'MTK') {
        _setupRole(DEFAULT_ADMIN_ROLE, admin);
        _setupRole(MINTER_ROLE, admin);
    }

    function mint(address to, uint256 amount) public {
        require(hasRole(MINTER_ROLE, msg.sender), 'Must have minter role to mint');
        _mint(to, amount);
    }

    function addMinter(address minter) public {
        grantRole(MINTER_ROLE, minter);
    }

    function removeMinter(address minter) public {
        revokeRole(MINTER_ROLE, minter);
    }
}