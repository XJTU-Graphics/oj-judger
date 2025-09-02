"""
函数提取模块

该模块负责使用 libclang 从 C++ 源文件中提取指定函数的完整实现。
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, List
from clang.cindex import (
    Index, Cursor, CursorKind,
    CompilationDatabase, CompileCommand
)
from judger.executor.function_types import FunctionSignature


logger = logging.getLogger('function_extractor')


class FunctionExtractor:
    """函数提取器类"""

    def __init__(self, build_dir: Path):
        """
        初始化函数提取器

        :param build_dir: 构建目录绝对路径，用于查找 compile_commands.json
        """
        self.index = Index.create()
        self.build_dir = build_dir
        self.compile_db: CompilationDatabase = CompilationDatabase.fromDirectory(build_dir)
        self._system_include_paths: Optional[List[str]] = None

    def _get_system_include_paths(self) -> List[str]:
        """
        获取 clang++ 的标准库 include path

        :return: 标准库 include path 列表
        :raises RuntimeError: 当无法获取 include path 时抛出
        """
        if self._system_include_paths is not None:
            return self._system_include_paths

        try:
            # 调用 clang++ 命令获取标准库搜索路径
            result = subprocess.run(
                ['clang++', '-E', '-x', 'c++', '-', '-v'],
                input='',
                capture_output=True,
                text=True,
                check=True
            )

            # 解析输出，提取 include path
            output = result.stderr

            # 查找包含路径的部分
            start_marker = '#include <...> search starts here:'
            end_marker = 'End of search list.'

            start_idx = output.find(start_marker)
            if start_idx == -1:
                raise RuntimeError('无法在 clang++ 输出中找到 include path 开始标记')

            end_idx = output.find(end_marker, start_idx)
            if end_idx == -1:
                raise RuntimeError('无法在 clang++ 输出中找到 include path 结束标记')

            # 提取路径部分
            paths_section = output[start_idx + len(start_marker):end_idx]

            # 按行分割并提取路径
            paths = []
            for line in paths_section.split('\n'):
                line = line.strip()
                if line and not line.startswith('ignoring nonexistent directory'):
                    paths.append(line)

            self._system_include_paths = paths
            logger.debug(f'获取到的系统 include paths: {paths}')
            return paths

        except subprocess.CalledProcessError as e:
            logger.error(f'调用 clang++ 命令失败: {e}')
            raise RuntimeError(f'获取系统 include path 失败: {e}') from e
        except Exception as e:
            logger.error(f'获取系统 include path 时发生错误: {e}')
            raise RuntimeError(f'获取系统 include path 失败: {e}') from e

    def extract_function_implementation(
        self,
        source_file_path: Path,
        function_signature: FunctionSignature
    ) -> Optional[str]:
        """
        从源文件中提取指定函数的实现

        :param source_file_path: 源文件绝对路径
        :param function_signature: 函数签名
        :return: 函数实现代码，如果未找到则返回None
        :raises RuntimeError: 当提取流程出现错误时抛出
        """
        try:
            # 查找编译命令
            compile_command: CompileCommand = self.compile_db.getCompileCommands(
                source_file_path
            )[0]

            if compile_command:
                # 使用编译命令解析源文件
                # 第一个参数是编译器，最后两个参数是源文件名，不应该传递给 libclang
                args = list(compile_command.arguments)[1:-2]

                # 添加系统 include path
                system_include_paths = self._get_system_include_paths()
                for path in system_include_paths:
                    args.extend(['-isystem', path])

                logger.debug(f'compilation args:\n{args}')
                tu = self.index.parse(str(source_file_path), args=args)
            else:
                # 如果找不到编译命令，抛出异常报错
                logger.warning(f'找不到 {source_file_path} 的编译命令')
                raise RuntimeError(f'compile command not found for {source_file_path}')

            logger.debug(f'try to find definition of {function_signature.name}')
            # 查找匹配的函数定义
            function_cursor = self._find_function_definition(tu.cursor, function_signature)

            if function_cursor is None:
                logger.warning(
                    f'未找到函数 {function_signature.name} 的定义'
                )
                return None
            else:
                logger.debug('definition found')

            # 提取函数实现
            implementation = self._extract_function_body(function_cursor)

            if implementation:
                logger.info(f'成功提取函数 {function_signature.name} 的实现')
            else:
                logger.warning(f'提取函数 {function_signature.name} 的实现失败')

            return implementation

        except RuntimeError:
            # 重新抛出 RuntimeError
            raise
        except Exception as e:
            logger.debug(f'{type(e)}')
            # 其他异常转换为 RuntimeError 并抛出
            logger.error(f'提取函数 {function_signature.name} 的实现时发生错误: {str(e)}')
            raise RuntimeError(f'提取函数实现失败: {str(e)}') from e

    def _find_function_definition(
        self,
        root_cursor: Cursor,
        function_signature: FunctionSignature
    ) -> Optional[Cursor]:
        """
        在AST中查找匹配的函数定义

        :param root_cursor: AST根节点
        :param function_signature: 函数签名
        :return: 匹配的函数定义节点，如果未找到则返回None
        """
        # 遍历AST查找函数定义
        for cursor in root_cursor.walk_preorder():
            if cursor.kind == CursorKind.FUNCTION_DECL or cursor.kind == CursorKind.CXX_METHOD:
                if self._is_function_match(cursor, function_signature):
                    return cursor

        return None

    def _is_function_match(
        self,
        function_cursor: Cursor,
        function_signature: FunctionSignature
    ) -> bool:
        """
        检查函数定义是否与给定的函数签名匹配

        :param function_cursor: 函数定义节点
        :param function_signature: 函数签名
        :return: 是否匹配
        :raises ValueError: 当函数名称包含多个 :: 时抛出
        """
        # 检查函数名
        name = function_signature.name

        # 检查是否为类方法（包含 ::）
        if '::' in name:
            parts = name.split('::')

            # 如果有多个 ::，抛出异常
            if len(parts) > 2:
                raise ValueError(f'不支持包含多个 :: 分隔符的函数名称 {name}')

            class_name = parts[0]
            method_name = parts[1]

            # 对于类方法，需要满足两个条件：
            # 1. 当前 cursor 的 spelling 属性等于方法名
            # 2. 当前 cursor 的 semantic_parent 游标的 kind 为 CursorKind.CLASS_DECL 且其 spelling 等于类名
            if function_cursor.spelling != method_name:
                return False

            # 检查父节点是否为类声明且类名匹配
            semantic_parent = function_cursor.semantic_parent
            if (semantic_parent is None or
                    semantic_parent.kind != CursorKind.CLASS_DECL or
                    semantic_parent.spelling != class_name):
                return False
        else:
            # 普通函数，直接检查名称
            if function_cursor.spelling != name:
                return False

        # 检查返回类型
        if function_cursor.result_type.spelling != function_signature.return_type:
            return False

        # 检查参数列表
        cursor_params = list(function_cursor.get_arguments())
        signature_params = function_signature.parameters

        if len(cursor_params) != len(signature_params):
            return False

        for cursor_param, signature_param in zip(cursor_params, signature_params):
            if cursor_param.type.spelling != signature_param.type:
                return False

        return True

    def _extract_function_body(self, function_cursor: Cursor) -> Optional[str]:
        """
        从函数定义节点中提取函数体

        :param function_cursor: 函数定义节点
        :return: 函数体代码，如果提取失败则返回None
        :raises RuntimeError: 当提取流程出现错误时抛出
        """
        try:
            # 获取函数体的范围
            body_cursor = None
            for child in function_cursor.get_children():
                if child.kind == CursorKind.COMPOUND_STMT:
                    body_cursor = child
                    break

            if body_cursor is None:
                logger.warning('函数没有函数体')
                return None

            # 获取源文件内容
            source_file = Path(function_cursor.location.file.name)
            if not source_file.is_absolute():
                source_file = self.build_dir.parent / source_file

            if not source_file.exists():
                raise RuntimeError(f'源文件不存在: {source_file}')

            with open(source_file, 'r', encoding='utf-8') as f:
                source_content = f.read()

            # 获取函数体的起始和结束位置
            start_location = function_cursor.extent.start
            end_location = body_cursor.extent.end

            # 将位置转换为行号和列号
            start_line = start_location.line - 1  # 转换为0-based
            start_column = start_location.column - 1
            end_line = end_location.line - 1
            end_column = end_location.column

            # 按行分割源代码
            lines = source_content.split('\n')

            # 提取函数体
            if start_line == end_line:
                # 单行函数体
                function_body = lines[start_line][start_column:end_column]
            else:
                # 多行函数体
                function_body = lines[start_line][start_column:] + '\n'
                for i in range(start_line + 1, end_line):
                    function_body += lines[i] + '\n'
                function_body += lines[end_line][:end_column]

            return function_body

        except (IndexError, IOError) as e:
            # 文件读取或索引错误，抛出异常
            logger.error(f'提取函数体时发生错误: {str(e)}')
            raise RuntimeError(f'提取函数体失败: {str(e)}') from e
        except Exception as e:
            # 其他异常，也抛出异常
            logger.error(f'提取函数体时发生未知错误: {str(e)}')
            raise RuntimeError(f'提取函数体失败: {str(e)}') from e


def extract_function_implementation(
    source_file_path: Path,
    function_signature: FunctionSignature,
    build_dir: Path
) -> Optional[str]:
    """
    从源文件中提取指定函数的实现

    :param source_file_path: 源文件绝对路径
    :param function_signature: 函数签名
    :param build_dir: 构建目录绝对路径，用于查找 compile_commands.json
    :return: 函数实现代码，如果未找到则返回None
    """
    extractor = FunctionExtractor(build_dir)
    return extractor.extract_function_implementation(source_file_path, function_signature)
